# FILE MAP
#   10-35  The frozen test split: sealed by default, and no tuning code asks for it.

from __future__ import annotations

import re
from pathlib import Path

import pytest

from evals.dataset import SealedSplitError, load_split

REPO = Path(__file__).resolve().parents[1]
# Files allowed to open the test split. TWEAK: add the final-eval runner when it exists.
ALLOWED = {"evals/dataset.py"}


def test_test_split_sealed_by_default(built, monkeypatch):
    root, _ = built
    monkeypatch.delenv("TRIAGEBENCH_FINAL_EVAL", raising=False)
    assert load_split("widgets", "dev", root=root)
    with pytest.raises(SealedSplitError):
        load_split("widgets", "test", root=root)


def test_no_tuning_code_reads_test_split():
    pat = re.compile(r"""load_split\([^)]*["']test["']""")
    offenders = [
        str(p.relative_to(REPO))
        for d in ("agent", "evals")
        for p in (REPO / d).rglob("*.py")
        if str(p.relative_to(REPO)) not in ALLOWED and pat.search(p.read_text())
    ]
    assert offenders == []
