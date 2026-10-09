# FILE MAP
#   30-50   sample_issues: which issues a run covers (seeded, so --limit is reproducible)
#   53-75   PredictionLog: append-only predictions.jsonl; reruns skip what's already done
#   78-120  run: drive the agent over a split through the replay MCP server
#   123-175 score_run / to_markdown: join predictions with t1 truth, metrics with 95% CIs
#   178-215 CLI
#
# Purpose: the eval harness. One run = one model x one split x the chosen tasks, written to its
# own folder so runs can be compared side by side.
#
# Usage:
#   uv run python -m evals.export_replay      # once: dev split -> ~/.cache/triagebench/replay
#   (cd mcp-server && npm ci && npm run build)
#   uv run --group agent python -m evals.harness run --model ollama:qwen3:8b --limit 20
#   uv run --group agent python -m evals.harness run --model google:gemini-2.5-flash --limit 20
#   uv run --group agent python -m evals.harness score ~/.cache/triagebench/runs/ollama-qwen3-8b

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from evals import config
from evals.dataset import load_split
from evals.stats import bootstrap_ci
from evals.tasks import dup, label

SCORERS = {"label": label, "dup": dup}


def sample_issues(issues: list[dict], limit: int | None, seed: int = 0) -> list[dict]:
    if limit is None or limit >= len(issues):
        return issues
    # TWEAK: the seed fixes which issues a --limit run sees, so two models get the same ones
    picked = random.Random(seed).sample(issues, limit)
    return sorted(picked, key=lambda i: i["number"])


def run_slug(model: str) -> str:
    return re.sub(r"[^\w.-]+", "-", model).strip("-")


class PredictionLog:
    """predictions.jsonl, one line per (task, repo, issue, sample). Appends survive a crash."""

    def __init__(self, path: Path):
        self.path = path
        self.done: set[tuple] = set()
        if path.exists():
            for line in path.read_text().splitlines():
                r = json.loads(line)
                self.done.add(self.key(r))

    @staticmethod
    def key(r: dict) -> tuple:
        return (r["task"], r["repo"], r["number"], r["sample"], r["prompt"], r["model"])

    def add(self, r: dict) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps(r, sort_keys=True) + "\n")
        self.done.add(self.key(r))


async def run(
    model,
    replay_dir: Path,
    out: Path,
    repos: list[str],
    tasks: list[str],
    split: str = "dev",
    limit: int | None = None,
    k: int = 1,
    data_root: Path = config.DATA_DIR,
    log: Callable[..., None] = print,
) -> Path:
    from agent.triage.agent import build_agent, prompt_hash, replay_toolset, run_task

    out.mkdir(parents=True, exist_ok=True)
    preds = PredictionLog(out / "predictions.jsonl")
    model_name = model if isinstance(model, str) else getattr(model, "model_name", "custom")
    toolset = replay_toolset(replay_dir)
    async with toolset:
        agents = {t: build_agent(t, model, toolset) for t in tasks}
        for key in repos:
            full = config.REPOS[key].full_name
            for issue in sample_issues(load_split(key, split, "t0", data_root), limit):
                for task in tasks:
                    for s in range(k):
                        meta = {"task": task, "repo": full, "number": issue["number"],
                                "sample": s, "prompt": prompt_hash(task), "model": model_name}
                        if PredictionLog.key(meta) in preds.done:
                            continue
                        res = await run_task(agents[task], task, full, issue["number"])
                        preds.add({**meta, **res.to_dict(), "repo_key": key, "split": split})
                        log(f"{task} {full}#{issue['number']} s{s}: "
                            f"{res.output if res.error is None else res.error}")
    (out / "run.json").write_text(json.dumps(
        {"model": model_name, "split": split, "repos": repos, "tasks": tasks,
         "limit": limit, "k": k}, indent=1, sort_keys=True) + "\n")
    return out


def replay_labels(replay_dir: Path) -> dict[str, set[str]]:
    """Each exported repo's label set, used to count proposals of labels that don't exist."""
    out = {}
    for bundle in replay_dir.glob("*/bundle.json"):
        full = json.loads(bundle.read_text())["full_name"]
        labels = json.loads((bundle.parent / "labels.json").read_text())
        out[full] = {lbl["name"] for lbl in labels}
    return out


def _rows(preds: list[dict], data_root: Path, labels: dict[str, set[str]]) -> dict[str, list]:
    splits: dict[tuple, tuple[dict, dict]] = {}
    rows: dict[str, list[dict]] = {}
    for p in preds:
        at = (p["repo_key"], p["split"])
        if at not in splits:
            splits[at] = tuple(
                {i["number"]: i for i in load_split(*at, part, data_root)} for part in ("t0", "t1")
            )
        t0, t1 = splits[at]
        rows.setdefault(p["task"], []).append({
            "t0": t0[p["number"]], "t1": t1[p["number"]], "output": p["output"],
            "repo": p["repo"], "pred": p, "valid_labels": labels.get(p["repo"]),
        })
    return rows


def score_run(out: Path, replay_dir: Path, data_root: Path = config.DATA_DIR) -> dict:
    preds = [json.loads(line) for line in (out / "predictions.jsonl").read_text().splitlines()]
    report: dict = {"run": json.loads((out / "run.json").read_text()), "tasks": {}}
    for task, rows in sorted(_rows(preds, data_root, replay_labels(replay_dir)).items()):
        scorer = SCORERS[task]
        groups = {"all": rows}
        for r in rows:
            groups.setdefault(r["repo"], []).append(r)
        task_rep = {}
        for name, grp in groups.items():
            m = scorer.score(grp)
            m["ci95"] = bootstrap_ci(grp, lambda s, sc=scorer: sc.score(s)[sc.HEADLINE])
            task_rep[name] = m
        task_rep["trace"] = {
            "tool_calls": dict(Counter(c for r in rows for c in r["pred"]["tool_calls"])),
            "errors": dict(Counter(r["pred"]["error"].split(":")[0] for r in rows
                                   if r["pred"]["error"])),
            "mean_seconds": sum(r["pred"]["seconds"] for r in rows) / len(rows),
            "mean_output_tokens": sum(r["pred"]["output_tokens"] for r in rows) / len(rows),
        }
        report["tasks"][task] = task_rep
    (out / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    (out / "report.md").write_text(to_markdown(report))
    return report


def to_markdown(report: dict) -> str:
    run = report["run"]
    lines = [f"# {run['model']} on {run['split']} (limit {run['limit']}, k={run['k']})", ""]
    for task, rep in report["tasks"].items():
        head = SCORERS[task].HEADLINE
        metrics = [k for k in rep["all"] if k not in ("ci95",)]
        lines += [f"## {task}", "", "| repo | " + " | ".join(metrics) + f" | {head} 95% CI |",
                  "|---" * (len(metrics) + 2) + "|"]
        for name, m in rep.items():
            if name == "trace":
                continue
            cells = [f"{m[k]:.3f}" if isinstance(m[k], float) else str(m[k]) for k in metrics]
            lo, hi = m["ci95"]
            lines.append(f"| {name} | " + " | ".join(cells) + f" | {lo:.3f} to {hi:.3f} |")
        t = rep["trace"]
        summary = (f"Tool calls: {t['tool_calls']}. Errors: {t['errors'] or 'none'}. "
                   f"Mean {t['mean_seconds']:.1f}s and {t['mean_output_tokens']:.0f} output "
                   "tokens per issue.")
        lines += ["", summary, ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run or score the triage eval.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--model", required=True, help="ollama:<tag> or any Pydantic AI model string")
    r.add_argument("--tasks", nargs="+", default=list(SCORERS), choices=list(SCORERS))
    r.add_argument("--repos", nargs="+", default=list(config.BACKTEST_REPOS))
    r.add_argument("--split", default="dev", choices=["dev", "test"])
    r.add_argument("--limit", type=int, help="issues per repo (seeded sample)")
    r.add_argument("--k", type=int, default=1, help="samples per issue")
    r.add_argument("--replay-dir", type=Path, default=config.cache_dir() / "replay")
    r.add_argument("--out", type=Path)
    s = sub.add_parser("score")
    s.add_argument("out", type=Path)
    s.add_argument("--replay-dir", type=Path, default=config.cache_dir() / "replay")
    for p in (r, s):
        p.add_argument("--data", type=Path, default=config.DATA_DIR)
    a = ap.parse_args(argv)
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

    if a.cmd == "run":
        out = a.out or config.cache_dir() / "runs" / run_slug(a.model)
        asyncio.run(run(a.model, a.replay_dir, out, a.repos, a.tasks, a.split, a.limit, a.k,
                        a.data))
    else:
        out = a.out
    score_run(out, a.replay_dir, a.data)
    print((out / "report.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
