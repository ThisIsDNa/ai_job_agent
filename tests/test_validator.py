"""Tests for blocking job draft validation."""

import pytest

from app.schemas.job_schema import JobPostingDraft
from app.validation.validator import validate_job_posting_draft


def _long_description() -> str:
    return "word " * 80  # well over 100 chars


def test_validate_blocks_empty_description() -> None:
    with pytest.raises(ValueError, match="description"):
        validate_job_posting_draft(
            {
                "url": "https://jobs.example.com/p/1",
                "description": "",
                "title": "T",
            }
        )


def test_validate_blocks_short_description() -> None:
    with pytest.raises(ValueError, match="too short"):
        validate_job_posting_draft(
            {
                "url": "https://jobs.example.com/p/1",
                "description": "short",
                "title": "T",
            }
        )


def test_validate_warns_on_missing_title() -> None:
    d = validate_job_posting_draft(
        {
            "url": "https://jobs.example.com/p/2",
            "description": _long_description(),
            "title": None,
            "company": "Acme",
            "location": "Remote",
        }
    )
    assert isinstance(d, JobPostingDraft)
    assert d.title is None
    assert "missing title" in d.validation_warnings


def test_validate_accepts_complete_draft() -> None:
    d = validate_job_posting_draft(
        {
            "url": "https://jobs.example.com/p/3",
            "title": "Engineer",
            "company": "Acme",
            "location": "NY",
            "description": _long_description(),
            "source": "jobs.example.com",
        }
    )
    assert d.validation_warnings == []
