# FILE MAP
#   12-30  Rebuild tests: same source + config gives byte-identical files; drift is detected
#   33-75  GitHubClient cache: offline rebuilds read cached bytes, token is not in the key

from __future__ import annotations

import httpx
import pytest

from evals import build_dataset
from evals.github_client import CacheMiss, GitHubClient, ResponseCache


def _snapshot_bytes(root):
    return {p.relative_to(root): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_rebuild_is_byte_identical(built, source, fake_config, tmp_path_factory):
    root, _ = built
    again = tmp_path_factory.mktemp("again")
    build_dataset.build_all(source, again, tuple(fake_config), log=lambda *_: None)
    assert _snapshot_bytes(root) == _snapshot_bytes(again)


def test_verify_passes_then_catches_drift(built, source):
    root, manifest = built
    assert build_dataset.verify(source, root) == []
    # A maintainer edits history after the freeze: verify must notice.
    num = manifest["repos"]["widgets"]["issues"][0]["number"]
    source.repos["acme/widgets"]["timelines"][num].append(
        {"event": "labeled", "created_at": "2025-01-01T00:00:00Z",
         "actor": {"login": "maintainer", "type": "User"}, "label": {"name": "late"}})
    assert any("t1 hash mismatch" in p for p in build_dataset.verify(source, root))


def test_split_sizes_and_exclusions(built):
    _, manifest = built
    for rec in manifest["repos"].values():
        splits = [e["split"] for e in rec["issues"]]
        assert (splits.count("test"), len(splits)) == (10, 30)
        assert rec["stats"]["excluded_edited"] > 0


def _transport(calls):
    def handler(request: httpx.Request):
        calls.append(request.url)
        nxt = '<https://api.github.com/items?page=2>; rel="next"'
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[{"n": 2}])
        return httpx.Response(200, json=[{"n": 1}], headers={"link": nxt})
    return httpx.MockTransport(handler)


def test_cache_serves_offline_and_ignores_token(tmp_path):
    calls = []
    cache = ResponseCache(tmp_path)
    live = GitHubClient(cache, token="tok-A", transport=_transport(calls))
    assert [x["n"] for x in live.paginate("/items")] == [1, 2]
    assert len(calls) == 2

    offline = GitHubClient(cache, token="tok-B", offline=True)
    assert [x["n"] for x in offline.paginate("/items")] == [1, 2]
    with pytest.raises(CacheMiss):
        offline.get("/never-fetched")


def test_rate_limit_waits_then_retries(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    seen = []

    def handler(request):
        seen.append(1)
        if len(seen) == 1:
            return httpx.Response(403, headers={"x-ratelimit-remaining": "0",
                                                "x-ratelimit-reset": "0"})
        return httpx.Response(200, json={"ok": True})

    gh = GitHubClient(ResponseCache(tmp_path), transport=httpx.MockTransport(handler))
    assert gh.get("/x") == {"ok": True} and len(seen) == 2
