# FILE MAP
#   8-45  Sampler tests: exact size, proportional strata, independence from input order.

from __future__ import annotations

import random
from collections import Counter

from evals.sample import split_test_dev, stratified_sample, stratum_of

ITEMS = [(n, ["bug"] if n % 3 else ["feature"]) for n in range(1, 301)]


def key(it):
    return it[1][0]


def num(it):
    return it[0]


def test_exact_size_and_proportional():
    s = stratified_sample(ITEMS, 90, key, num, "seed")
    assert len(s) == 90
    assert Counter(key(i) for i in s) == {"bug": 60, "feature": 30}


def test_order_independent_and_seeded():
    shuffled = ITEMS[:]
    random.Random(1).shuffle(shuffled)
    assert stratified_sample(ITEMS, 50, key, num, "s") == stratified_sample(shuffled, 50, key, num, "s")
    assert stratified_sample(ITEMS, 50, key, num, "s") != stratified_sample(ITEMS, 50, key, num, "t")


def test_split_disjoint_and_complete():
    test, dev = split_test_dev(ITEMS[:120], 40, key, num, "s")
    assert len(test) == 40 and len(dev) == 80
    assert not {num(t) for t in test} & {num(d) for d in dev}


def test_stratum_prefers_common_label():
    freq = Counter({"bug": 10, "area/cli": 3})
    assert stratum_of(["area/cli", "bug"], freq) == "bug"
    assert stratum_of([], freq) == "_none"
