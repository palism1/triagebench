# FILE MAP
#   14-25   helpers: timestamps and actors in GitHub's JSON shape
#   28-95   make_repo: a deterministic synthetic repo history with every case the builder handles
#   98-125  FakeSource: implements evals.build_dataset.Source over that history
#
# Purpose: offline fixtures shaped like real GitHub REST responses, so builder tests run in CI
# without a token. Each issue's later events plant "LEAK" markers the t0 side must never see.

from __future__ import annotations

import copy
import random
from datetime import UTC, datetime, timedelta

BASE = datetime(2024, 1, 1, tzinfo=UTC)
HUMAN = {"login": "maintainer", "type": "User"}
BOT = {"login": "triage-agent[bot]", "type": "Bot"}
AUTHOR = {"login": "reporter", "type": "User"}


def ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_repo(full_name: str = "acme/widgets", n: int = 60, seed: int = 7) -> dict:
    rng = random.Random(seed)
    issues, timelines = [], {}
    kinds = ["bug", "bug", "bug", "feature", "question"]
    areas = ["area/cli", "area/solver", "area/docs"]
    for k in range(1, n + 1):
        created = BASE + timedelta(days=k)
        number = k
        is_pr = k % 10 == 0
        closed = created + timedelta(days=3) if k % 3 else None
        kind = rng.choice(kinds)
        area = rng.choice(areas)
        issue = {
            "number": number,
            "html_url": f"https://github.com/{full_name}/issues/{number}",
            "title": f"LEAKTITLE renamed later {number}" if k % 4 == 0 else f"Issue {number}",
            "body": f"Steps to reproduce issue {number}",
            "user": AUTHOR,
            "author_association": "NONE",
            "created_at": ts(created),
            "closed_at": ts(closed) if closed else None,
            "state": "closed" if closed else "open",
            "state_reason": ("duplicate" if k % 7 == 0 else "completed") if closed else None,
            "labels": [{"name": kind}, {"name": area}],
        }
        if is_pr:
            issue["pull_request"] = {"url": "x"}
        issues.append(issue)

        later = created + timedelta(hours=5)
        tl = [
            # issue-form label in the creation window (visible at t0)
            {"event": "labeled", "created_at": ts(created + timedelta(seconds=5)),
             "actor": AUTHOR, "label": {"name": kind}},
            # human triage after t0 (ground truth)
            {"event": "labeled", "created_at": ts(later), "actor": HUMAN, "label": {"name": area}},
            # bot label after t0 (excluded from ground truth)
            {"event": "labeled", "created_at": ts(later), "actor": BOT,
             "label": {"name": "needs-triage"}},
            {"event": "commented", "created_at": ts(later + timedelta(minutes=1)), "user": HUMAN,
             "body": f"LEAK fixed in v{number}.0"},
        ]
        if k % 4 == 0:
            tl.append({"event": "renamed", "created_at": ts(later), "actor": HUMAN,
                       "rename": {"from": f"Issue {number}", "to": issue["title"]}})
        if k % 5 == 0:  # human adds then removes a label: must not count
            tl += [
                {"event": "labeled", "created_at": ts(later), "actor": HUMAN,
                 "label": {"name": "LEAK-wontfix"}},
                {"event": "unlabeled", "created_at": ts(later + timedelta(hours=1)),
                 "actor": HUMAN, "label": {"name": "LEAK-wontfix"}},
            ]
        if k % 7 == 0 and k > 1:
            tl.append({"event": "commented", "created_at": ts(later), "user": HUMAN,
                       "body": f"Duplicate of #{k - 1}"})
        if closed and k % 2:
            tl.append({"event": "closed", "created_at": ts(closed), "actor": HUMAN,
                       "commit_id": f"{number:040x}"})
            tl.append({"event": "cross-referenced", "created_at": ts(closed), "actor": HUMAN,
                       "source": {"issue": {"number": 1000 + number,
                                            "pull_request": {"merged_at": ts(closed)},
                                            "repository": {"full_name": full_name}}}})
        timelines[number] = tl
    edited = {i["number"]: (ts(BASE + timedelta(days=i["number"], hours=30))
                            if i["number"] % 11 == 0 else None) for i in issues}
    return {"full_name": full_name, "issues": issues, "timelines": timelines, "edited": edited}


class FakeSource:
    def __init__(self, repos: dict[str, dict]):
        self.repos = repos  # full_name -> make_repo() output

    def list_issues(self, repo: str) -> list[dict]:
        return copy.deepcopy(self.repos[repo]["issues"])

    def timeline(self, repo: str, number: int) -> list[dict]:
        return copy.deepcopy(self.repos[repo]["timelines"][number])

    def t0_sha(self, repo: str, created_at: str) -> str:
        # Deterministic stand-in for "last commit before created_at".
        return created_at[:10].replace("-", "").ljust(40, "a")

    def last_edited(self, repo: str, numbers: list[int]) -> dict[int, str | None]:
        return {n: self.repos[repo]["edited"].get(n) for n in numbers}
