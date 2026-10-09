# FILE MAP
#   10-45  Leakage tests: nothing that happened after t0 may appear in any t0 snapshot.

from __future__ import annotations

import json

from evals.dataset import load_split
from evals.snapshot import T0_FIELDS, parse_ts


def _all_t0(root, repos, monkeypatch):
    monkeypatch.setenv("TRIAGEBENCH_FINAL_EVAL", "1")  # test-only: read both splits
    return [r for k in repos for s in ("dev", "test") for r in load_split(k, s, "t0", root)]


def test_t0_has_only_whitelisted_fields(built, fake_config, monkeypatch):
    root, _ = built
    for row in _all_t0(root, fake_config, monkeypatch):
        assert set(row) == T0_FIELDS


def test_no_post_t0_text_or_labels_in_t0(built, fake_config, monkeypatch):
    root, _ = built
    for row in _all_t0(root, fake_config, monkeypatch):
        # The fakes plant "LEAK" in later comments, later titles and later labels.
        assert "LEAK" not in json.dumps(row), row["number"]


def test_t1_labels_never_shown_as_t0_labels(built, fake_config, monkeypatch):
    root, _ = built
    monkeypatch.setenv("TRIAGEBENCH_FINAL_EVAL", "1")
    for k in fake_config:
        for s in ("dev", "test"):
            t0s = load_split(k, s, "t0", root)
            t1s = load_split(k, s, "t1", root)
            for t0, t1 in zip(t0s, t1s, strict=True):
                assert t0["number"] == t1["number"]
                assert not set(t0["labels_at_t0"]) & set(t1["human_labels_added"])


def test_open_index_precedes_t0(built, fake_config, source, monkeypatch):
    root, _ = built
    created = {i["number"]: i["created_at"]
               for repo in source.repos.values() for i in repo["issues"]}
    for row in _all_t0(root, fake_config, monkeypatch):
        t0 = parse_ts(row["created_at"])
        assert all(parse_ts(created[n]) < t0 for n in row["open_issues_at_t0"])
