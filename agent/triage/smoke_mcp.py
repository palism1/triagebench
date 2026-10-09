# FILE MAP
#   14-25  server_params: how to launch the built TypeScript server over stdio
#   28-50  smoke: connect, list tools, call each read tool once on one issue
#   53-65  CLI
#
# Purpose: prove the Python side can reach the MCP server before the agent exists (Week 2).
# Usage: (cd mcp-server && npm run build) && uv run --group agent python -m agent.triage.smoke_mcp \
#          --replay-dir ~/.cache/triagebench/replay --repo astral-sh/ruff --number 12345

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parents[2] / "mcp-server" / "dist" / "index.js"


def server_params(replay_dir: Path) -> StdioServerParameters:
    return StdioServerParameters(command="node", args=[str(SERVER), "--replay-dir", str(replay_dir)])


async def smoke(replay_dir: Path, repo: str, number: int) -> dict:
    async with (
        stdio_client(server_params(replay_dir)) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = sorted(t.name for t in (await session.list_tools()).tools)
        results = {}
        for name, args in [
            ("get_issue", {"repo": repo, "number": number}),
            ("list_labels", {"repo": repo}),
            ("search_dup", {"repo": repo, "number": number, "k": 3}),
        ]:
            res = await session.call_tool(name, args)
            if res.is_error:  # mcp>=2 uses snake_case result fields
                raise RuntimeError(f"{name} failed: {res.content[0].text}")
            results[name] = json.loads(res.content[0].text)
        return {"tools": tools, **results}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--replay-dir", type=Path, required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--number", type=int, required=True)
    a = ap.parse_args()
    print(json.dumps(asyncio.run(smoke(a.replay_dir, a.repo, a.number)), indent=1)[:4000])


if __name__ == "__main__":
    main()
