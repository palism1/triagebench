# FILE MAP
#   12-90  Unit tests for build_t0 / build_t1 on hand-built timelines (one case per rule).

from __future__ import annotations

from evals.config import RepoConfig
from evals.snapshot import build_t0, build_t1, is_bot

CFG = RepoConfig("acme/widgets", bot_logins=frozenset({"helperbot"}))
HUMAN = {"login": "maint", "type": "User"}
AUTHOR = {"login": "reporter", "type": "User"}


def issue(number=5, created="2024-03-01T10:00:00Z", **kw):
    base = {
        "number": number, "html_url": f"https://github.com/acme/widgets/issues/{number}",
        "title": "Current title", "body": "body", "user": AUTHOR, "author_association": "NONE",
        "created_at": created, "closed_at": None, "state": "open", "state_reason": None,
        "labels": [],
    }
    return base | kw


def lab(name, at, actor=HUMAN, kind="labeled"):
    return {"event": kind, "created_at": at, "actor": actor, "label": {"name": name}}


def test_template_labels_are_t0_and_not_ground_truth():
    tl = [lab("bug", "2024-03-01T10:00:03Z", AUTHOR), lab("area/cli", "2024-03-01T12:00:00Z")]
    t0 = build_t0(issue(), tl, "s" * 40, [], CFG)
    t1 = build_t1(issue(), tl, CFG)
    assert t0.labels_at_t0 == ["bug"]
    assert t1.human_labels_added == ["area/cli"]


def test_bot_labels_excluded_including_configured_logins():
    tl = [
        lab("needs-triage", "2024-03-01T12:00:00Z", {"login": "x[bot]", "type": "Bot"}),
        lab("p1", "2024-03-01T12:00:00Z", {"login": "helperbot", "type": "User"}),
    ]
    t1 = build_t1(issue(), tl, CFG)
    assert t1.human_labels_added == []
    assert t1.bot_labels_added == ["needs-triage", "p1"]
    assert is_bot(None, CFG)


def test_label_removed_later_is_not_ground_truth():
    tl = [lab("wontfix", "2024-03-01T12:00:00Z"),
          lab("wontfix", "2024-03-02T12:00:00Z", kind="unlabeled")]
    assert build_t1(issue(), tl, CFG).human_labels_added == []


def test_rename_is_undone_in_t0():
    tl = [{"event": "renamed", "created_at": "2024-03-02T00:00:00Z", "actor": HUMAN,
           "rename": {"from": "Original", "to": "Middle"}},
          {"event": "renamed", "created_at": "2024-03-03T00:00:00Z", "actor": HUMAN,
           "rename": {"from": "Middle", "to": "Current title"}}]
    assert build_t0(issue(), tl, "s" * 40, [], CFG).title == "Original"


def test_duplicate_from_maintainer_comment_but_not_author():
    by_author = [{"event": "commented", "created_at": "2024-03-02T00:00:00Z", "user": AUTHOR,
                  "body": "maybe duplicate of #3?"}]
    assert build_t1(issue(), by_author, CFG).duplicate_of is None
    by_maint = [{"event": "commented", "created_at": "2024-03-02T00:00:00Z", "user": HUMAN,
                 "body": "Duplicate of https://github.com/acme/widgets/issues/3"}]
    t1 = build_t1(issue(), by_maint, CFG)
    assert (t1.duplicate_of, t1.is_duplicate) == (3, True)


def test_state_reason_duplicate_without_link():
    t1 = build_t1(issue(state="closed", state_reason="duplicate"), [], CFG)
    assert t1.is_duplicate and t1.duplicate_of is None


def test_closing_commit_and_merged_prs_only():
    tl = [
        {"event": "closed", "created_at": "2024-03-05T00:00:00Z", "actor": HUMAN,
         "commit_id": "c" * 40},
        {"event": "cross-referenced", "created_at": "2024-03-04T00:00:00Z", "source": {"issue": {
            "number": 9, "pull_request": {"merged_at": "2024-03-05T00:00:00Z"},
            "repository": {"full_name": "acme/widgets"}}}},
        {"event": "cross-referenced", "created_at": "2024-03-04T00:00:00Z", "source": {"issue": {
            "number": 10, "pull_request": {"merged_at": None},
            "repository": {"full_name": "acme/widgets"}}}},
        {"event": "cross-referenced", "created_at": "2024-03-04T00:00:00Z", "source": {"issue": {
            "number": 11, "pull_request": {"merged_at": "2024-03-05T00:00:00Z"},
            "repository": {"full_name": "other/repo"}}}},
    ]
    t1 = build_t1(issue(), tl, CFG)
    assert t1.closing_commit_sha == "c" * 40
    assert t1.referenced_prs == [9]


def test_open_index_is_issues_open_at_t0_only():
    others = [
        issue(1, "2024-02-01T00:00:00Z"),                                   # open: in
        issue(2, "2024-02-01T00:00:00Z", closed_at="2024-02-15T00:00:00Z"),  # closed before: out
        issue(3, "2024-02-01T00:00:00Z", closed_at="2024-03-09T00:00:00Z"),  # closed after: in
        issue(4, "2024-04-01T00:00:00Z"),                                   # created after: out
        issue(6, "2024-02-01T00:00:00Z", pull_request={"url": "x"}),        # PR: out
    ]
    t0 = build_t0(issue(), [], "s" * 40, others + [issue()], CFG)
    assert t0.open_issues_at_t0 == [1, 3]
