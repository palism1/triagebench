# FILE MAP
#   20-30   canonical_json / content_hash: the byte format every hash and rebuild check uses
#   33-48   is_bot: who counts as automation
#   51-75   T0Snapshot: what was visible when the issue was created
#   78-95   T1Truth: what maintainers did afterwards (ground truth)
#   98-140  build_t0: pure function from cached API JSON to a T0Snapshot
#   143-215 build_t1: pure function from the issue timeline to T1Truth
#
# Purpose: separate "what the agent may see" (t0) from "what it is graded against" (t1).
# Both builders are pure: same inputs, same bytes. The leakage tests in tests/ rely on that.

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from evals.config import RepoConfig


def canonical_json(obj) -> str:
    # DO NOT TOUCH: changing separators/ordering changes every hash in the manifest.
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def content_hash(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def is_bot(actor: dict | None, cfg: RepoConfig) -> bool:
    if not actor:
        return True  # ghost/deleted accounts: unknown provenance, so not ground truth
    login = actor.get("login", "")
    return (
        actor.get("type") == "Bot"
        or login.endswith("[bot]")
        or login in cfg.bot_logins
    )


@dataclass(frozen=True)
class T0Snapshot:
    """Everything the agent may read. No field may depend on events after t0."""

    repo: str
    number: int
    url: str
    created_at: str
    title: str  # original title (renames undone)
    body: str
    author_association: str
    labels_at_t0: list[str]  # issue-form labels applied in the creation window
    t0_sha: str  # last default-branch commit before created_at
    open_issues_at_t0: list[int]  # duplicate-search universe

    def to_dict(self) -> dict:
        return asdict(self)


T0_FIELDS = frozenset(T0Snapshot.__dataclass_fields__)


@dataclass(frozen=True)
class T1Truth:
    """What maintainers did after t0. Never shown to the agent."""

    repo: str
    number: int
    human_labels_added: list[str]
    bot_labels_added: list[str]
    state: str
    state_reason: str | None
    closed_at: str | None
    is_duplicate: bool
    duplicate_of: int | None
    closing_commit_sha: str | None
    referenced_prs: list[int]

    def to_dict(self) -> dict:
        return asdict(self)


def _events(timeline: list[dict]) -> list[dict]:
    # Comments carry created_at; most events too. Stable sort keeps API order on ties.
    return sorted(timeline, key=lambda e: e.get("created_at") or e.get("submitted_at") or "")


def build_t0(
    issue: dict,
    timeline: list[dict],
    t0_sha: str,
    all_issues: list[dict],
    cfg: RepoConfig,
) -> T0Snapshot:
    created = parse_ts(issue["created_at"])
    window_end = created + timedelta(seconds=cfg.template_window_s)

    labels: set[str] = set()
    title = issue["title"]
    first_rename = True
    for ev in _events(timeline):
        kind = ev.get("event")
        if kind == "renamed" and first_rename:
            title = ev["rename"]["from"]  # undo every later rename
            first_rename = False
        at = ev.get("created_at")
        if not at or parse_ts(at) > window_end:
            continue
        if kind == "labeled":
            labels.add(ev["label"]["name"])
        elif kind == "unlabeled":
            labels.discard(ev["label"]["name"])

    open_at_t0 = sorted(
        o["number"]
        for o in all_issues
        if "pull_request" not in o
        and o["number"] != issue["number"]
        and parse_ts(o["created_at"]) < created
        and (o.get("closed_at") is None or parse_ts(o["closed_at"]) > created)
    )
    return T0Snapshot(
        repo=cfg.full_name,
        number=issue["number"],
        url=issue["html_url"],
        created_at=issue["created_at"],
        title=title,
        body=issue.get("body") or "",
        author_association=issue.get("author_association", "NONE"),
        labels_at_t0=sorted(labels),
        t0_sha=t0_sha,
        open_issues_at_t0=open_at_t0,
    )


def _dup_patterns(repo: str) -> list[re.Pattern]:
    return [
        re.compile(r"(?i)\bduplicate\s+(?:of|to)\s+#(\d+)"),
        re.compile(rf"(?i)\bduplicate\s+(?:of|to)\s+https://github\.com/{re.escape(repo)}/issues/(\d+)"),
    ]


def build_t1(issue: dict, timeline: list[dict], cfg: RepoConfig) -> T1Truth:
    created = parse_ts(issue["created_at"])
    window_end = created + timedelta(seconds=cfg.template_window_s)

    human: set[str] = set()
    bot: set[str] = set()
    t0_labels: set[str] = set()
    duplicate_of: int | None = None
    marked_dup = False
    closing_sha: str | None = None
    prs: set[int] = set()
    patterns = _dup_patterns(cfg.full_name)

    for ev in _events(timeline):
        kind = ev.get("event")
        at = ev.get("created_at")
        in_window = bool(at) and parse_ts(at) <= window_end
        if kind == "labeled":
            name = ev["label"]["name"]
            if in_window:
                t0_labels.add(name)
            elif is_bot(ev.get("actor"), cfg):
                bot.add(name)
            elif name not in t0_labels:
                human.add(name)
        elif kind == "unlabeled":
            name = ev["label"]["name"]
            human.discard(name)
            bot.discard(name)
            if in_window:
                t0_labels.discard(name)
        elif kind == "marked_as_duplicate":
            marked_dup = True
        elif kind == "commented" and duplicate_of is None:
            # Only maintainers' (or anyone but the author's) comments count as a dup verdict.
            if (ev.get("user") or ev.get("actor") or {}).get("login") == issue["user"]["login"]:
                continue
            for pat in patterns:
                if m := pat.search(ev.get("body") or ""):
                    duplicate_of = int(m.group(1))
                    break
        elif kind == "closed" and ev.get("commit_id"):
            closing_sha = ev["commit_id"]
        elif kind == "cross-referenced":
            src = (ev.get("source") or {}).get("issue") or {}
            pr = src.get("pull_request")
            same_repo = (src.get("repository") or {}).get("full_name") == cfg.full_name
            if pr and same_repo and pr.get("merged_at"):
                prs.add(src["number"])

    if duplicate_of == issue["number"]:
        duplicate_of = None
    is_dup = (
        issue.get("state_reason") == "duplicate"
        or marked_dup
        or duplicate_of is not None
        or any(lbl.lower() == "duplicate" for lbl in human)
    )
    return T1Truth(
        repo=cfg.full_name,
        number=issue["number"],
        human_labels_added=sorted(human),
        bot_labels_added=sorted(bot),
        state=issue["state"],
        state_reason=issue.get("state_reason"),
        closed_at=issue.get("closed_at"),
        is_duplicate=is_dup,
        duplicate_of=duplicate_of,
        closing_commit_sha=closing_sha,
        referenced_prs=sorted(prs),
    )
