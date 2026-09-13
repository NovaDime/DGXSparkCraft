from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TERMINAL_STATUSES = {"completed", "needs_review", "cancelled", "failed", "interrupted"}
MIN_ROUNDS = 3
MAX_ROUNDS = 4
DEFAULT_ROUNDS = 3


class MeetingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    topic: str = Field(min_length=4, max_length=4000)
    constraints: str = Field(default="", max_length=4000)
    max_rounds: int = Field(default=DEFAULT_ROUNDS, ge=MIN_ROUNDS, le=MAX_ROUNDS, strict=True)


class Concern(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=300)
    detail: str = Field(min_length=1, max_length=2500)
    severity: Literal["blocker", "major", "minor"] = "major"


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    summary: str = Field(min_length=1, max_length=6000)
    stance: Literal["approve", "revise"]
    proposal: str = Field(default="", max_length=12000)
    concerns: list[Concern] = Field(default_factory=list, max_length=8)
    recommendations: list[str] = Field(default_factory=list, max_length=12)
    resolved_issue_ids: list[str] = Field(default_factory=list, max_length=100)
    skill_ids: list[str] = Field(default_factory=list, max_length=10)
    usage: dict = Field(default_factory=dict)

    @field_validator("recommendations", "resolved_issue_ids", "skill_ids")
    @classmethod
    def bound_strings(cls, values: list[str]) -> list[str]:
        if any(len(value) > 2500 for value in values):
            raise ValueError("返回条目超过长度限制")
        return values
