"""Structured task result payload for pipeline operations."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TaskResult(BaseModel):
    ok: bool
    state: str | None = None
    message: str
    data: dict = Field(default_factory=dict)
    error_code: str | None = None
    retryable: bool = False
    suggested_action: str | None = None
