# FILE MAP
#   22-40  replay_toolset: the MCP server over stdio, read tools only
#   43-60  prompt_text / prompt_hash: versioned task instructions
#   63-80  build_agent: one Pydantic AI agent per task
#   83-125 run_task: triage one issue, returning the decision plus a trace summary
#
# Purpose: the triage agent, v0. Zero-shot, no guardrails: every later guardrail is measured
# against these numbers, so this file stays plain on purpose.

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from fastmcp.client import Client
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models import Model

from agent.triage.models import model_settings, resolve_model, wants_no_think
from agent.triage.outputs import DupDecision, LabelDecision

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "mcp-server" / "dist" / "index.js"
PROMPTS = Path(__file__).parent / "prompts"

TASKS: dict[str, type] = {"label": LabelDecision, "dup": DupDecision}
# DO NOT TOUCH: v0 sees read tools only. Writes go through propose_* once the queue exists.
READ_TOOLS = frozenset({"get_issue", "list_labels", "search_dup", "get_file"})


def replay_toolset(replay_dir: Path) -> MCPToolset:
    transport = StdioTransport(command="node", args=[str(SERVER), "--replay-dir", str(replay_dir)])
    return MCPToolset(Client(transport), tool_error_behavior="retry", max_retries=2)


def prompt_text(task: str) -> str:
    return (PROMPTS / f"{task}.md").read_text()


def prompt_hash(task: str) -> str:
    return hashlib.sha256(prompt_text(task).encode()).hexdigest()[:12]


def build_agent(task: str, model: str | Model, toolset) -> Agent:
    instructions = prompt_text(task)
    if wants_no_think(model):
        instructions += "\n/no_think\n"
    return Agent(
        resolve_model(model),
        output_type=TASKS[task],
        instructions=instructions,
        toolsets=[toolset.filtered(lambda _ctx, tool: tool.name in READ_TOOLS)],
        model_settings=model_settings(),
        retries=2,
    )


@dataclass
class TaskResult:
    task: str
    repo: str
    number: int
    output: dict | None
    error: str | None = None
    tool_calls: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0

    def to_dict(self) -> dict:
        return dict(self.__dict__)


async def run_task(agent: Agent, task: str, repo: str, number: int) -> TaskResult:
    """Run one task on one issue. Failures are recorded, not raised: they are part of the score."""
    start = time.monotonic()
    try:
        result = await agent.run(f"Repository: {repo}\nIssue: #{number}")
    except Exception as e:  # noqa: BLE001 - any model or tool failure counts as a miss
        return TaskResult(task, repo, number, None, f"{type(e).__name__}: {e}"[:500],
                          seconds=round(time.monotonic() - start, 3))
    calls = [p.tool_name for m in result.all_messages() for p in m.parts
             if isinstance(p, ToolCallPart) and not p.tool_name.startswith("final_result")]
    usage = result.usage
    return TaskResult(
        task, repo, number, result.output.model_dump(),
        tool_calls=calls,
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        seconds=round(time.monotonic() - start, 3),
    )
