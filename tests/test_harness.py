# FILE MAP
#   20-60  scripted_model: a deterministic stand-in for an LLM that uses the MCP tools
#   63-80  replay fixture: the synthetic dataset exported the way the real one will be
#   83-125 end-to-end: run -> predictions -> report; reruns resume; the test split stays sealed
#
# Purpose: the whole loop (agent -> MCP server -> harness -> scores) runs in CI with no model,
# no token and no network. Skipped until `npm run build` has produced mcp-server/dist.

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

pytest.importorskip("pydantic_ai")

from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from evals import harness
from evals.dataset import SealedSplitError
from evals.export_replay import export_repo

SERVER = Path(__file__).resolve().parents[1] / "mcp-server/dist/index.js"
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not SERVER.exists(), reason="run `npm run build` in mcp-server/ first"),
]


def _returns(messages) -> dict:
    out = {}
    for m in messages:
        for p in m.parts:
            if isinstance(p, ToolReturnPart):
                c = p.content
                out[p.tool_name] = json.loads(c) if isinstance(c, str) else c
    return out


def scripted(messages, info: AgentInfo) -> ModelResponse:
    """get_issue, then list_labels (label task) or search_dup (dup task), then answer."""
    prompt = messages[0].parts[-1].content
    repo, number = re.search(r"Repository: (\S+)\nIssue: #(\d+)", prompt).groups()
    ref = {"repo": repo, "number": int(number)}
    seen = _returns(messages)
    is_dup = "search_dup" in (info.instructions or "")
    if "get_issue" not in seen:
        return ModelResponse(parts=[ToolCallPart("get_issue", ref)])
    if is_dup and "search_dup" not in seen:
        return ModelResponse(parts=[ToolCallPart("search_dup", {**ref, "k": 3})])
    if not is_dup and "list_labels" not in seen:
        return ModelResponse(parts=[ToolCallPart("list_labels", {"repo": repo})])
    if is_dup:
        hits = seen["search_dup"]
        answer = {"duplicate_of": hits[0]["number"] if hits else None, "rationale": "top hit"}
    else:
        answer = {"labels": [seen["list_labels"][0]["name"]], "rationale": "first label"}
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, answer)])


@pytest.fixture
def replay(built, source, tmp_path):
    root, _ = built
    out = tmp_path / "replay"
    for key in ("widgets", "gadgets"):
        export_repo(source, key, "dev", root, out)
    return root, out


def _run(root, replay_dir, out, **kw):
    return asyncio.run(harness.run(
        FunctionModel(scripted, model_name="scripted"), replay_dir, out,
        ["widgets", "gadgets"], ["label", "dup"], data_root=root, log=lambda *_: None, **kw))


def test_end_to_end_run_and_score(replay, tmp_path):
    root, replay_dir = replay
    out = _run(root, replay_dir, tmp_path / "run", limit=4)
    preds = [json.loads(line) for line in (out / "predictions.jsonl").read_text().splitlines()]
    assert len(preds) == 2 * 2 * 4  # repos x tasks x issues
    assert all(p["error"] is None for p in preds), [p["error"] for p in preds if p["error"]]
    assert {tuple(p["tool_calls"]) for p in preds} == {
        ("get_issue", "list_labels"), ("get_issue", "search_dup")}

    report = harness.score_run(out, replay_dir, root)
    for task in ("label", "dup"):
        rep = report["tasks"][task]
        assert rep["all"]["n"] <= 8 and set(rep) >= {"all", "acme/widgets", "acme/gadgets"}
        lo, hi = rep["all"]["ci95"]
        assert 0.0 <= lo <= hi <= 1.0
    assert "| all |" in (out / "report.md").read_text()


def test_rerun_resumes_instead_of_repeating(replay, tmp_path):
    root, replay_dir = replay
    out = _run(root, replay_dir, tmp_path / "run", limit=2)
    before = (out / "predictions.jsonl").read_text()
    _run(root, replay_dir, out, limit=2)
    assert (out / "predictions.jsonl").read_text() == before


def test_sampling_is_seeded():
    issues = [{"number": n} for n in range(100)]
    assert harness.sample_issues(issues, 10) == harness.sample_issues(issues, 10)


def test_test_split_stays_sealed(replay, tmp_path, monkeypatch):
    monkeypatch.delenv("TRIAGEBENCH_FINAL_EVAL", raising=False)
    root, replay_dir = replay
    with pytest.raises(SealedSplitError):
        _run(root, replay_dir, tmp_path / "run", split="test", limit=1)
