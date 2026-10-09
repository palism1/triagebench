# FILE MAP
#   15-30  added_labels: what the agent proposes to add, net of labels already on the issue
#   33-70  score: micro precision / recall / F1, exact match, invalid-label rate
#
# Purpose: score the label task against what maintainers did (decision D2). Truth is
# t1.human_labels_added; labels the issue form applied at t0 are inputs, never targets.
#
# Row shape: {"t0": <t0 record>, "t1": <t1 record>, "output": <LabelDecision dict or None>,
#             "valid_labels": <set of label names the repo uses, or None if unknown>}

from __future__ import annotations


def added_labels(t0: dict, output: dict | None) -> set[str]:
    if not output:
        return set()
    return set(output.get("labels") or []) - set(t0.get("labels_at_t0") or [])


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def score(rows: list[dict]) -> dict:
    tp = fp = fn = exact = invalid = proposed = failed = 0
    for row in rows:
        pred = added_labels(row["t0"], row["output"])
        truth = set(row["t1"]["human_labels_added"])
        tp += len(pred & truth)
        fp += len(pred - truth)
        fn += len(truth - pred)
        exact += pred == truth
        proposed += len(pred)
        if row.get("valid_labels") is not None:
            invalid += len(pred - row["valid_labels"])
        failed += row["output"] is None
    p, r, f = _prf(tp, fp, fn)
    n = len(rows)
    return {
        "n": n,
        "precision": p,
        "recall": r,
        "f1": f,
        "exact_match": exact / n if n else 0.0,
        # labels that don't exist in the repo: a guardrail target, reported separately
        "invalid_label_rate": invalid / proposed if proposed else 0.0,
        "failed": failed,
    }


HEADLINE = "f1"
