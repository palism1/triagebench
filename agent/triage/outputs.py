# FILE MAP
#   8-20  LabelDecision / DupDecision: the structured answer each task agent must return
#
# Purpose: the agent's output contract. The eval harness scores these fields and nothing else.

from __future__ import annotations

from pydantic import BaseModel, Field


class LabelDecision(BaseModel):
    labels: list[str] = Field(description="label names to add, from list_labels")
    rationale: str


class DupDecision(BaseModel):
    duplicate_of: int | None = Field(description="issue number this duplicates, or null")
    rationale: str
