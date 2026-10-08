# FILE MAP
#   8-25   RepoConfig: per-repo settings (bots, template window, cutoff)
#   28-55  REPOS: the three backtest repos plus the alternate
#   58-70  Global dataset settings (sample sizes, seed, cache location)
#
# Purpose: one place for every value the dataset builder depends on, so a rebuild with the
# same config and the same cache produces the same bytes.

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class RepoConfig:
    full_name: str
    # Accounts whose label events never count as ground truth, on top of any `[bot]` login
    # or actor with type "Bot". TWEAK: extend when the survey finds more automation accounts.
    bot_logins: frozenset[str] = field(default_factory=frozenset)
    # Labels applied within this many seconds of creation count as t0 (issue-form labels).
    # TWEAK: 120 s covers form labels and slow webhooks without swallowing human triage.
    template_window_s: int = 120


REPOS: dict[str, RepoConfig] = {
    "ruff": RepoConfig("astral-sh/ruff"),
    "poetry": RepoConfig("python-poetry/poetry"),
    # pydantic-ai runs several AI agents that label issues. `douwebot` is named in its
    # workflows (inferred to be an automation account; confirm with survey_repos.py).
    "pydantic-ai": RepoConfig("pydantic/pydantic-ai", bot_logins=frozenset({"douwebot"})),
    "promptfoo": RepoConfig("promptfoo/promptfoo"),  # alternate, TypeScript
}

# CHANGE ME: the three repos the dataset is built from (keys of REPOS).
BACKTEST_REPOS: tuple[str, ...] = ("ruff", "poetry", "pydantic-ai")

# Issues created after this date are skipped so every sampled issue has settled ground truth.
# TWEAK: move forward only when rebuilding the whole dataset (it changes every split).
CREATED_BEFORE = datetime(2026, 6, 30, tzinfo=UTC)
CREATED_AFTER = datetime(2023, 1, 1, tzinfo=UTC)

# Bodies edited later than this after creation are excluded (they may leak t1 text). See D6.
EDIT_GRACE_S = 3600

SAMPLE_PER_REPO = 300
TEST_PER_REPO = 100
# DO NOT TOUCH: changing the seed after the test split is tagged silently changes the split.
SEED = 20261008

DATA_DIR = Path(__file__).parent / "data"


def cache_dir() -> Path:
    return Path(os.environ.get("TRIAGEBENCH_CACHE_DIR", "~/.cache/triagebench")).expanduser()
