"""Schema for parsed job posting draft objects."""

from __future__ import annotations

from pydantic import BaseModel, Field


class JobPostingDraft(BaseModel):
    """Validated job posting draft from deterministic HTML parsing."""

    title: str | None = None
    company: str | None = None
    location: str | None = None
    url: str
    description: str
    source: str | None = None
    validation_warnings: list[str] = Field(default_factory=list)
