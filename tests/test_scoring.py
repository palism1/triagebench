# FILE MAP
#   12-45  label task scoring: net-of-t0 predictions, micro F1, invalid labels, failures
#   48-80  duplicate task scoring: unscorable rows, reachable recall
#   83-90  bootstrap is seeded
#
# Purpose: the metrics in every report are exactly what these tests say they are.

from __future__ import annotations

from evals.stats import bootstrap_ci
from evals.tasks import dup, label


def lrow(t0_labels, truth, out, valid=frozenset({"bug", "area/cli", "area/docs"})):
    return {"t0": {"labels_at_t0": t0_labels}, "t1": {"human_labels_added": truth},
            "output": None if out is None else {"labels": out, "rationale": ""},
            "valid_labels": set(valid)}


def test_label_ignores_labels_already_on_the_issue():
    m = label.score([lrow(["bug"], ["area/cli"], ["bug", "area/cli"])])
    assert (m["precision"], m["recall"], m["exact_match"]) == (1.0, 1.0, 1.0)


def test_label_micro_f1_and_invalid_rate():
    m = label.score([
        lrow([], ["area/cli"], ["area/cli", "made-up"]),  # tp 1, fp 1 (invalid)
        lrow([], ["area/docs"], []),                      # fn 1
        lrow([], [], []),                                 # exact, nothing to add
    ])
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["f1"] == 0.5
    assert m["exact_match"] == 1 / 3
    assert m["invalid_label_rate"] == 0.5


def test_label_failure_counts_as_empty_prediction():
    m = label.score([lrow([], ["bug"], None)])
    assert m["failed"] == 1 and m["recall"] == 0.0


def test_label_unknown_label_set_skips_invalid_rate():
    row = lrow([], ["x"], ["y"])
    row["valid_labels"] = None
    assert label.score([row])["invalid_label_rate"] == 0.0


def drow(truth, pred, open_at_t0=(1, 2, 3), is_dup=None, failed=False):
    return {"t0": {"open_issues_at_t0": list(open_at_t0)},
            "t1": {"duplicate_of": truth,
                   "is_duplicate": truth is not None if is_dup is None else is_dup},
            "output": None if failed else {"duplicate_of": pred, "rationale": ""}}


def test_dup_metrics():
    m = dup.score([
        drow(2, 2),            # hit, reachable
        drow(9, None),         # miss, target closed before t0 (unreachable)
        drow(None, None),      # correct non-duplicate
        drow(None, 3),         # false positive
        drow(None, None, is_dup=True),  # closed as duplicate, target unknown: dropped
    ])
    assert m["n"] == 4 and m["unscorable"] == 1
    assert m["accuracy"] == 0.5
    assert m["precision"] == 0.5
    assert m["recall"] == 0.5 and m["recall_reachable"] == 1.0
    assert (m["duplicates"], m["reachable"]) == (2, 1)


def test_dup_failure_is_counted():
    assert dup.score([drow(None, None, failed=True)])["failed"] == 1


def test_bootstrap_is_seeded():
    rows = list(range(50))
    mean = lambda s: sum(s) / len(s)
    assert bootstrap_ci(rows, mean) == bootstrap_ci(rows, mean)
    lo, hi = bootstrap_ci(rows, mean)
    assert lo < 24.5 < hi
