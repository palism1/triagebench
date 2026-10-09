# FILE MAP
#   19-60   survey_repo: label hygiene numbers for one repo from a seeded sample of issues
#   63-80   to_markdown: the table that goes into docs/decisions.md
#   83-110  CLI
#
# Purpose: decide the 3 backtest repos on measured label hygiene, not reputation.
# Usage: uv run python -m evals.survey_repos --repos ruff poetry pydantic-ai promptfoo
#   (needs GITHUB_TOKEN; ~100 timeline calls per repo plus the issue list, all cached)

from __future__ import annotations

import argparse
import random
import statistics
import sys
from datetime import UTC, datetime, timedelta

from evals import config
from evals.build_dataset import GitHubSource, Source
from evals.github_client import GitHubClient, ResponseCache, load_token
from evals.snapshot import build_t1, is_bot, parse_ts


def survey_repo(src: Source, key: str, n: int = 100, years: int = 2) -> dict:
    cfg = config.REPOS[key]
    since = datetime.now(UTC) - timedelta(days=365 * years)
    issues = [
        i
        for i in src.list_issues(cfg.full_name)
        if "pull_request" not in i and parse_ts(i["created_at"]) >= since
    ]
    sample = sorted(issues, key=lambda i: i["number"])
    random.Random(f"{config.SEED}:survey:{key}").shuffle(sample)
    sample = sample[:n]

    with_human = dup = human_events = bot_events = 0
    hours_to_label: list[float] = []
    for i in sample:
        tl = src.timeline(cfg.full_name, i["number"])
        t1 = build_t1(i, tl, cfg)
        with_human += bool(t1.human_labels_added)
        dup += t1.is_duplicate
        created = parse_ts(i["created_at"])
        window_end = created + timedelta(seconds=cfg.template_window_s)
        first_human = None
        for ev in tl:
            if ev.get("event") != "labeled" or parse_ts(ev["created_at"]) <= window_end:
                continue
            if is_bot(ev.get("actor"), cfg):
                bot_events += 1
            else:
                human_events += 1
                at = parse_ts(ev["created_at"])
                first_human = at if first_human is None else min(first_human, at)
        if first_human:
            hours_to_label.append((first_human - created).total_seconds() / 3600)

    total_events = human_events + bot_events
    return {
        "repo": cfg.full_name,
        "issues_last_2y": len(issues),
        "sampled": len(sample),
        "pct_with_human_label": round(100 * with_human / max(1, len(sample)), 1),
        "pct_label_events_by_bots": round(100 * bot_events / max(1, total_events), 1),
        "pct_duplicates": round(100 * dup / max(1, len(sample)), 1),
        "median_hours_to_human_label": (
            round(statistics.median(hours_to_label), 1) if hours_to_label else None
        ),
    }


def to_markdown(rows: list[dict]) -> str:
    cols = list(rows[0])
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repos", nargs="*", default=list(config.REPOS))
    ap.add_argument("-n", type=int, default=100)
    args = ap.parse_args(argv)
    token = load_token()
    if not token:
        print("GITHUB_TOKEN missing: see .env.example", file=sys.stderr)
        return 2
    src = GitHubSource(GitHubClient(ResponseCache(config.cache_dir()), token=token))
    print(to_markdown([survey_repo(src, k, args.n) for k in args.repos]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
