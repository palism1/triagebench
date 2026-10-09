# FILE MAP
#   17-30  scorable: drop issues closed as duplicate whose target we couldn't recover
#   33-75  score: accuracy, duplicate precision / recall, recall on reachable targets
#
# Purpose: score the duplicate task. Truth is t1.duplicate_of; null means "not a duplicate".
# "Reachable" means the true target was open at t0, so search_dup could have returned it.
#
# Row shape: {"t0": <t0 record>, "t1": <t1 record>, "output": <DupDecision dict or None>}

from __future__ import annotations


def scorable(row: dict) -> bool:
    t1 = row["t1"]
    return not (t1["is_duplicate"] and t1["duplicate_of"] is None)


def predicted(row: dict) -> int | None:
    out = row["output"]
    return out.get("duplicate_of") if out else None


def score(rows: list[dict]) -> dict:
    kept = [r for r in rows if scorable(r)]
    correct = pred_dup = true_dup = hit = reachable = reachable_hit = failed = 0
    for row in kept:
        truth = row["t1"]["duplicate_of"]
        pred = predicted(row)
        correct += pred == truth
        failed += row["output"] is None
        if pred is not None:
            pred_dup += 1
        if truth is not None:
            true_dup += 1
            hit += pred == truth
            if truth in row["t0"]["open_issues_at_t0"]:
                reachable += 1
                reachable_hit += pred == truth
    n = len(kept)
    return {
        "n": n,
        "unscorable": len(rows) - n,
        "accuracy": correct / n if n else 0.0,
        "precision": hit / pred_dup if pred_dup else 0.0,
        "recall": hit / true_dup if true_dup else 0.0,
        "recall_reachable": reachable_hit / reachable if reachable else 0.0,
        "duplicates": true_dup,
        "reachable": reachable,
        "failed": failed,
    }


HEADLINE = "accuracy"
