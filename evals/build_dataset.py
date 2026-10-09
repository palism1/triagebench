# FILE MAP
#   24-85   GitHubSource: the few GitHub reads the builder needs (all cached)
#   88-150  build_repo: pool -> exclusions -> oversample -> timelines -> final sample -> split
#   153-185 build_all: every backtest repo + manifest
#   188-215 verify: offline rebuild from the cache must reproduce every manifest hash
#   218-250 CLI
#
# Purpose: turn live GitHub history into a frozen, hash-checked backtest dataset.
# Usage:
#   uv run python -m evals.build_dataset build            # needs GITHUB_TOKEN, fills the cache
#   uv run python -m evals.build_dataset verify           # offline; fails on any drift

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Protocol

from evals import config
from evals.config import RepoConfig
from evals.dataset import read_manifest, write_manifest, write_repo
from evals.github_client import GitHubClient, ResponseCache, load_token
from evals.sample import split_test_dev, stratified_sample, stratum_of
from evals.snapshot import build_t0, build_t1, content_hash, parse_ts


class Source(Protocol):
    def list_issues(self, repo: str) -> list[dict]: ...
    def timeline(self, repo: str, number: int) -> list[dict]: ...
    def t0_sha(self, repo: str, created_at: str) -> str: ...
    def last_edited(self, repo: str, numbers: list[int]) -> dict[int, str | None]: ...
    def labels(self, repo: str) -> list[dict]: ...


class GitHubSource:
    def __init__(self, client: GitHubClient):
        self.gh = client
        self._branch: dict[str, str] = {}

    def list_issues(self, repo: str) -> list[dict]:
        # The issues endpoint also returns PRs; callers drop items with "pull_request".
        return list(
            self.gh.paginate(f"/repos/{repo}/issues", state="all", sort="created", direction="asc")
        )

    def timeline(self, repo: str, number: int) -> list[dict]:
        return list(self.gh.paginate(f"/repos/{repo}/issues/{number}/timeline"))

    def t0_sha(self, repo: str, created_at: str) -> str:
        if repo not in self._branch:
            self._branch[repo] = self.gh.get(f"/repos/{repo}")["default_branch"]
        commits = self.gh.get(
            f"/repos/{repo}/commits", sha=self._branch[repo], until=created_at, per_page=1
        )
        return commits[0]["sha"]

    def labels(self, repo: str) -> list[dict]:
        # Current label set; repos rarely delete labels, so this approximates the t0 set.
        return list(self.gh.paginate(f"/repos/{repo}/labels"))

    def last_edited(self, repo: str, numbers: list[int]) -> dict[int, str | None]:
        owner, name = repo.split("/")
        out: dict[int, str | None] = {}
        for i in range(0, len(numbers), 50):
            chunk = numbers[i : i + 50]
            fields = " ".join(f"i{n}: issue(number: {n}) {{ lastEditedAt }}" for n in chunk)
            q = f'query {{ repository(owner: "{owner}", name: "{name}") {{ {fields} }} }}'
            data = self.gh.graphql(q)["repository"]
            out.update({n: (data.get(f"i{n}") or {}).get("lastEditedAt") for n in chunk})
        return out


def _eligible(issue: dict) -> bool:
    if "pull_request" in issue:
        return False
    created = parse_ts(issue["created_at"])
    return config.CREATED_AFTER <= created < config.CREATED_BEFORE


def build_repo(
    src: Source, key: str, cfg: RepoConfig, n: int, n_test: int, seed: int, log=print
) -> tuple[list, dict]:
    all_issues = src.list_issues(cfg.full_name)
    pool = [i for i in all_issues if _eligible(i)]

    # Stage 1: oversample 2x by *current* labels (cheap proxy), so we fetch timelines for
    # ~2n issues instead of the whole history. TWEAK: raise the factor if exclusions bite.
    cur_freq = Counter(lbl["name"] for i in pool for lbl in i["labels"])
    over = stratified_sample(
        pool,
        min(len(pool), 2 * n),
        key=lambda i: stratum_of([lbl["name"] for lbl in i["labels"]], cur_freq),
        number=lambda i: i["number"],
        seed=f"{seed}:{key}:over",
    )

    # Stage 2: drop bodies edited after the grace period (possible t1 leakage, decision D6).
    edited = src.last_edited(cfg.full_name, [i["number"] for i in over])
    grace = timedelta(seconds=config.EDIT_GRACE_S)
    kept = []
    for i in over:
        e = edited.get(i["number"])
        if e is None or parse_ts(e) <= parse_ts(i["created_at"]) + grace:
            kept.append(i)
    stats = {"pool": len(pool), "oversampled": len(over), "excluded_edited": len(over) - len(kept)}

    # Stage 3: build t0/t1 and re-stratify by true ground truth (human labels after t0).
    built = []
    for i in kept:
        tl = src.timeline(cfg.full_name, i["number"])
        t0 = build_t0(i, tl, src.t0_sha(cfg.full_name, i["created_at"]), all_issues, cfg)
        built.append((t0, build_t1(i, tl, cfg)))
    truth_freq = Counter(lbl for _, t1 in built for lbl in t1.human_labels_added)

    def stratum(r):
        return stratum_of(r[1].human_labels_added, truth_freq)

    def num(r):
        return r[0].number

    final = stratified_sample(built, n, stratum, num, f"{seed}:{key}:final")
    test, dev = split_test_dev(final, n_test, stratum, num, f"{seed}:{key}")
    rows = [("test", *r) for r in test] + [("dev", *r) for r in dev]
    stats.update(sampled=len(final), test=len(test), dev=len(dev))
    log(f"{key}: {stats}")
    return rows, stats


def _settings() -> dict:
    return {
        "created_after": config.CREATED_AFTER.isoformat(),
        "created_before": config.CREATED_BEFORE.isoformat(),
        "edit_grace_s": config.EDIT_GRACE_S,
        "sample_per_repo": config.SAMPLE_PER_REPO,
        "test_per_repo": config.TEST_PER_REPO,
        "seed": config.SEED,
    }


def build_all(src: Source, root: Path, repos=config.BACKTEST_REPOS, log=print) -> dict:
    manifest = {"version": 1, "settings": _settings(), "repos": {}}
    for key in repos:
        cfg = config.REPOS[key]
        rows, stats = build_repo(
            src, key, cfg, config.SAMPLE_PER_REPO, config.TEST_PER_REPO, config.SEED, log
        )
        entries = write_repo(root, key, rows)
        manifest["repos"][key] = {"full_name": cfg.full_name, "stats": stats, "issues": entries}
    write_manifest(root, manifest)
    return manifest


def verify(src: Source, root: Path) -> list[str]:
    """Rebuild each manifest issue from the source and return every mismatch (empty = OK)."""
    manifest = read_manifest(root)
    problems = []
    for key, rec in manifest["repos"].items():
        cfg = config.REPOS[key]
        all_issues = src.list_issues(cfg.full_name)
        by_num = {i["number"]: i for i in all_issues}
        for e in rec["issues"]:
            issue = by_num[e["number"]]
            tl = src.timeline(cfg.full_name, e["number"])
            t0 = build_t0(issue, tl, e["t0_sha"], all_issues, cfg)
            if t0.t0_sha != src.t0_sha(cfg.full_name, issue["created_at"]):
                problems.append(f"{key}#{e['number']}: t0 SHA changed")
            if content_hash(t0.to_dict()) != e["t0_hash"]:
                problems.append(f"{key}#{e['number']}: t0 hash mismatch")
            if content_hash(build_t1(issue, tl, cfg).to_dict()) != e["t1_hash"]:
                problems.append(f"{key}#{e['number']}: t1 hash mismatch")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["build", "verify"])
    ap.add_argument("--repos", nargs="*", default=list(config.BACKTEST_REPOS))
    ap.add_argument("--out", type=Path, default=config.DATA_DIR)
    args = ap.parse_args(argv)

    offline = args.command == "verify"
    if offline and not (args.out / "manifest.json").exists():
        print(f"no manifest in {args.out}: run `build` first", file=sys.stderr)
        return 2
    token = load_token()
    if not offline and not token:
        print("GITHUB_TOKEN missing: see .env.example", file=sys.stderr)
        return 2
    client = GitHubClient(ResponseCache(config.cache_dir()), token=token, offline=offline)
    src = GitHubSource(client)
    if args.command == "build":
        build_all(src, args.out, tuple(args.repos))
        return 0
    problems = verify(src, args.out)
    for p in problems:
        print(p)
    print("OK: rebuild matches manifest" if not problems else f"{len(problems)} mismatches")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
