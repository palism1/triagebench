# FILE MAP
#   17-30   stratum_of: the label an issue is stratified by
#   33-60   stratified_sample: seeded, proportional (largest remainder) sampling
#   63-75   split_test_dev: carve the frozen test split out of a repo's sample
#
# Purpose: deterministic sampling. Same pool + same seed = same issues, regardless of the
# order the pool arrives in (everything is sorted by issue number before shuffling).

from __future__ import annotations

import random
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")
NONE = "_none"


def stratum_of(labels: Sequence[str], freq: Counter) -> str:
    """The issue's most common label across the pool (ties broken alphabetically)."""
    if not labels:
        return NONE
    return min(labels, key=lambda lbl: (-freq[lbl], lbl))


def stratified_sample(
    items: Sequence[T],
    n: int,
    key: Callable[[T], str],
    number: Callable[[T], int],
    seed: str,
) -> list[T]:
    groups: dict[str, list[T]] = defaultdict(list)
    for it in items:
        groups[key(it)].append(it)
    total = len(items)
    if n >= total:
        return sorted(items, key=number)

    # Largest-remainder allocation so strata sizes sum exactly to n.
    quotas = {s: n * len(g) / total for s, g in groups.items()}
    alloc = {s: int(q) for s, q in quotas.items()}
    leftover = n - sum(alloc.values())
    for s in sorted(quotas, key=lambda s: (-(quotas[s] - alloc[s]), s))[:leftover]:
        alloc[s] += 1

    picked: list[T] = []
    for s in sorted(groups):
        g = sorted(groups[s], key=number)
        random.Random(f"{seed}:{s}").shuffle(g)
        picked.extend(g[: alloc[s]])
    return sorted(picked, key=number)


def split_test_dev(
    items: Sequence[T], n_test: int, key: Callable[[T], str], number: Callable[[T], int], seed: str
) -> tuple[list[T], list[T]]:
    test = stratified_sample(items, n_test, key, number, f"{seed}:test")
    test_ids = {number(t) for t in test}
    dev = [it for it in sorted(items, key=number) if number(it) not in test_ids]
    return test, dev
