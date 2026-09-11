"""Structured-output schemas for the four LLM-backed nodes.

These are the JSON schemas the model must satisfy. They are intentionally separate
from the persisted models so prompt-facing shapes can evolve without migrations.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GeneralizedVariable(BaseModel):
    name: str
    source: str
    description: str


class GeneralizedStep(BaseModel):
    action: Literal["jira.create_issue", "slack.post_message", "gmail.apply_label"]
    title: str
    field_names: list[str] = Field(description="Ordered field names for this action")
    field_templates: list[str] = Field(
        description="Template for each field, same order as field_names, using {variable}"
    )
    produces: list[str]


class GeneralizeOutput(BaseModel):
    name: str = Field(description="Short workflow name, max 6 words")
    trigger_description: str
    subject_keywords: list[str]
    body_keywords: list[str]
    variables: list[GeneralizedVariable]
    steps: list[GeneralizedStep]
    estimated_manual_seconds: int


class MatchOutput(BaseModel):
    matches: bool
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(description="One sentence the user will see")


class PlannedValue(BaseModel):
    name: str
    value: str


class PlanOutput(BaseModel):
    values: list[PlannedValue]
    notes: str = Field(description="One sentence on any judgement calls made")


class RiskOutput(BaseModel):
    external_messages: int
    records_created: int
    records_modified: int
    records_deleted: int
    blast_radius: str
    level: Literal["low", "medium", "high"]
