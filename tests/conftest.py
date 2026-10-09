# FILE MAP
#   8-30  Fixtures: a two-repo synthetic history, small sample sizes, and a built dataset.
#
# Purpose: every builder test runs offline on tests/fakes.py data.

from __future__ import annotations

import pytest

from evals import build_dataset, config
from evals.config import RepoConfig
from tests.fakes import FakeSource, make_repo


@pytest.fixture
def fake_config(monkeypatch):
    repos = {
        "widgets": RepoConfig("acme/widgets"),
        "gadgets": RepoConfig("acme/gadgets", bot_logins=frozenset({"maintainer-bot"})),
    }
    monkeypatch.setattr(config, "REPOS", repos)
    monkeypatch.setattr(config, "SAMPLE_PER_REPO", 30)
    monkeypatch.setattr(config, "TEST_PER_REPO", 10)
    return repos


@pytest.fixture
def source(fake_config):
    return FakeSource({cfg.full_name: make_repo(cfg.full_name, seed=i)
                       for i, cfg in enumerate(fake_config.values())})


@pytest.fixture
def built(tmp_path, source, fake_config):
    manifest = build_dataset.build_all(source, tmp_path, tuple(fake_config), log=lambda *_: None)
    return tmp_path, manifest
