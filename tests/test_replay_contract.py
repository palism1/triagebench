# FILE MAP
#   14-35  The Python exporter writes exactly the bundle shape the TypeScript server reads
#   38-50  Exported bundles never contain ground truth or later issues
#   53-75  Smoke: the Python MCP client reaches the built server (skipped if not built)

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.export_replay import BUNDLE_FILES, export_repo

TS_FIXTURE = Path(__file__).resolve().parents[1] / "mcp-server/test/fixtures/replay/widgets"


def _keys(path: Path) -> set[str]:
    if path.suffix == ".jsonl":
        return set(json.loads(path.read_text().splitlines()[0]))
    data = json.loads(path.read_text())
    return set(data[0] if isinstance(data, list) else data)


def test_export_matches_server_fixture_shape(built, source, tmp_path):
    root, _ = built
    out = export_repo(source, "widgets", "dev", root, tmp_path)
    for name in BUNDLE_FILES:
        assert _keys(out / name) == _keys(TS_FIXTURE / name), name


def test_bundle_has_no_ground_truth_or_future_issues(built, source, tmp_path):
    root, _ = built
    out = export_repo(source, "widgets", "dev", root, tmp_path)
    text = "".join((out / n).read_text() for n in BUNDLE_FILES)
    assert "LEAK" not in text.replace("LEAKTITLE", "")  # corpus titles are current (D7)
    assert "human_labels_added" not in text and "duplicate_of" not in text
    issues = [json.loads(line) for line in (out / "issues.jsonl").read_text().splitlines()]
    allowed = {n for i in issues for n in i["open_issues_at_t0"]}
    corpus = {json.loads(line)["number"] for line in (out / "corpus.jsonl").read_text().splitlines()}
    assert corpus <= allowed


SERVER = Path(__file__).resolve().parents[1] / "mcp-server/dist/index.js"


@pytest.mark.smoke
@pytest.mark.skipif(not SERVER.exists(), reason="run `npm run build` in mcp-server/ first")
def test_python_client_reaches_server():
    mcp = pytest.importorskip("mcp")  # noqa: F841
    import asyncio

    from agent.triage.smoke_mcp import smoke

    out = asyncio.run(smoke(TS_FIXTURE.parent, "acme/widgets", 12))
    assert out["tools"] == sorted(
        ["get_file", "get_issue", "list_labels", "propose_label", "propose_pr", "search_dup"]
    )
    assert out["get_issue"]["number"] == 12
    assert out["search_dup"][0]["number"] == 3
