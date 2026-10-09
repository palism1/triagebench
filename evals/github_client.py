# FILE MAP
#   14-24   load_token: read GITHUB_TOKEN from env or ~/.config/triagebench/.env
#   27-60   ResponseCache: one JSON file per request, keyed by a hash of method+URL+body
#   63-150  GitHubClient: GET/paginate/GraphQL with caching, rate-limit waits, offline mode
#
# Purpose: every GitHub response the dataset depends on goes through this cache, so a rebuild
# reads the same bytes instead of the live API (which changes as maintainers keep working).

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

API = "https://api.github.com"


def load_token() -> str | None:
    if tok := os.environ.get("GITHUB_TOKEN"):
        return tok
    env = Path("~/.config/triagebench/.env").expanduser()
    if env.exists():
        for line in env.read_text().splitlines():
            key, _, val = line.partition("=")
            if key.strip() == "GITHUB_TOKEN" and val.strip():
                return val.strip()
    return None


class CacheMiss(LookupError):
    """Raised in offline mode when a request has no cached response."""


class ResponseCache:
    def __init__(self, root: Path):
        self.root = root

    @staticmethod
    def key(method: str, url: str, body: Any = None) -> str:
        raw = json.dumps([method, url, body], sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict | None:
        p = self._path(key)
        return json.loads(p.read_text()) if p.exists() else None

    def put(self, key: str, entry: dict) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry, sort_keys=True))
        tmp.replace(p)


class GitHubClient:
    """Read-only GitHub REST/GraphQL client. It has no methods that write to GitHub."""

    def __init__(
        self,
        cache: ResponseCache,
        token: str | None = None,
        offline: bool = False,
        transport: httpx.BaseTransport | None = None,
    ):
        self.cache = cache
        self.offline = offline
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "triagebench-dataset-builder",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.http = httpx.Client(headers=headers, timeout=30, transport=transport)

    # DO NOT TOUCH: the cache key must not include the token or headers, or a rebuild with a
    # different token would miss every cached response.
    def _request(self, method: str, url: str, body: Any = None) -> dict:
        key = self.cache.key(method, url, body)
        if (hit := self.cache.get(key)) is not None:
            return hit
        if self.offline:
            raise CacheMiss(f"{method} {url}")
        for attempt in range(6):
            resp = self.http.request(method, url, json=body)
            if resp.status_code in (403, 429) and self._wait_for_limit(resp, attempt):
                continue
            resp.raise_for_status()
            entry = {"json": resp.json(), "next": resp.links.get("next", {}).get("url")}
            self.cache.put(key, entry)
            return entry
        raise RuntimeError(f"rate limited too many times: {url}")

    @staticmethod
    def _wait_for_limit(resp: httpx.Response, attempt: int) -> bool:
        if retry := resp.headers.get("retry-after"):  # secondary rate limit
            time.sleep(int(retry))
            return True
        if resp.headers.get("x-ratelimit-remaining") == "0":
            reset = int(resp.headers.get("x-ratelimit-reset", time.time() + 60))
            time.sleep(max(1, reset - int(time.time())) + 1)
            return True
        if resp.status_code == 429:
            time.sleep(2**attempt)
            return True
        return False

    def get(self, path: str, **params: Any) -> Any:
        return self._request("GET", self._url(path, params))["json"]

    def paginate(self, path: str, **params: Any) -> Iterator[Any]:
        params.setdefault("per_page", 100)
        url: str | None = self._url(path, params)
        while url:
            entry = self._request("GET", url)
            yield from entry["json"]
            url = entry["next"]

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        body = {"query": query, "variables": variables or {}}
        data = self._request("POST", f"{API}/graphql", body)["json"]
        if data.get("errors"):
            raise RuntimeError(data["errors"])
        return data["data"]

    @staticmethod
    def _url(path: str, params: dict) -> str:
        url = path if path.startswith("http") else f"{API}{path}"
        if params:
            q = str(httpx.QueryParams(sorted(params.items())))
            url = f"{url}?{q}"
        return url
