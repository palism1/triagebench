# FILE MAP
#   20-60  export_repo: one repo's split -> replay bundle (t0 issues, dup corpus, labels)
#   63-95  CLI
#
# Purpose: write the bundle the TypeScript MCP server serves in replay mode. Only t0 data goes
# in; ground truth (t1) never leaves evals/data. The test split is exported only through
# load_split's final-eval switch.
#
# Usage:
#   uv run python -m evals.export_replay                    # dev split -> ~/.cache/triagebench/replay
#   TRIAGEBENCH_FINAL_EVAL=1 uv run python -m evals.export_replay --split test --out <dir>

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evals import config
from evals.build_dataset import GitHubSource, Source
from evals.dataset import load_split
from evals.github_client import GitHubClient, ResponseCache, load_token
from evals.snapshot import canonical_json

BUNDLE_FILES = ("bundle.json", "issues.jsonl", "corpus.jsonl", "labels.json")


def export_repo(src: Source, key: str, split: str, data_root: Path, out: Path) -> Path:
    cfg = config.REPOS[key]
    issues = load_split(key, split, "t0", data_root)
    by_num = {i["number"]: i for i in src.list_issues(cfg.full_name) if "pull_request" not in i}
    needed = sorted({n for i in issues for n in i["open_issues_at_t0"]})
    # Known simplification (decision D7): corpus entries use each candidate's current title
    # and body. The issue under test is fully t0; its duplicate candidates may carry later edits.
    corpus = [
        {"number": n, "title": by_num[n]["title"], "body": by_num[n].get("body") or ""}
        for n in needed
        if n in by_num
    ]
    labels = sorted(
        ({"name": lbl["name"], "description": lbl.get("description") or ""}
         for lbl in src.labels(cfg.full_name)),
        key=lambda lbl: lbl["name"],
    )

    d = out / key
    d.mkdir(parents=True, exist_ok=True)
    (d / "bundle.json").write_text(
        json.dumps({"full_name": cfg.full_name, "split": split}, sort_keys=True) + "\n"
    )
    (d / "issues.jsonl").write_text("".join(canonical_json(i) + "\n" for i in issues))
    (d / "corpus.jsonl").write_text("".join(canonical_json(c) + "\n" for c in corpus))
    (d / "labels.json").write_text(json.dumps(labels, indent=1, sort_keys=True) + "\n")
    return d


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repos", nargs="*", default=list(config.BACKTEST_REPOS))
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--data", type=Path, default=config.DATA_DIR)
    ap.add_argument("--out", type=Path, default=config.cache_dir() / "replay")
    args = ap.parse_args(argv)
    # Offline when the cache is warm from `build`; falls back to the API with a token.
    client = GitHubClient(ResponseCache(config.cache_dir()), token=load_token())
    for key in args.repos:
        print(export_repo(GitHubSource(client), key, args.split, args.data, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
