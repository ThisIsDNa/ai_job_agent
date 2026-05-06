"""Integration bridge tests for Resume Tailor callable adapter."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from app.integrations.resume_tailor_bridge import (
    _load_tailor_resume_callable,
    ResumeTailorUnavailableError,
    tailor_resume_for_job,
)


def test_bridge_calls_tailor_resume_with_expected_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    resume = tmp_path / "base_resume.docx"
    resume.write_bytes(b"docx-bytes")

    called: dict = {}

    def fake_tailor_resume(*, resume_docx_path: str, job_description: str, context: str):
        called["resume_docx_path"] = resume_docx_path
        called["job_description"] = job_description
        called["context"] = context
        return {
            "tailored_resume_sections": {
                "summary": ["Tailored summary text."],
                "experience": ["Improved bullet one", "Improved bullet two"],
            },
            "top_alignment_highlights": ["SQL alignment"],
            "top_gaps_to_watch": ["Domain gap"],
        }

    monkeypatch.setattr(
        "app.integrations.resume_tailor_bridge._load_tailor_resume_callable",
        lambda: fake_tailor_resume,
    )

    out = tailor_resume_for_job(
        {
            "title": "Business Analyst",
            "company": "Acme",
            "description": "Need SQL and stakeholder management",
        },
        str(resume),
    )

    assert called["resume_docx_path"] == str(resume)
    assert called["job_description"] == "Need SQL and stakeholder management"
    assert called["context"] == "Target role: Business Analyst at Acme"
    assert out["tailored_summary"] == "Tailored summary text."
    assert out["updated_experience"] == ["Improved bullet one", "Improved bullet two"]


def test_bridge_handles_missing_callable_dependency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    resume = tmp_path / "base_resume.docx"
    resume.write_bytes(b"docx-bytes")

    def raise_unavailable():
        raise ResumeTailorUnavailableError("Resume Tailor unavailable for import")

    monkeypatch.setattr(
        "app.integrations.resume_tailor_bridge._load_tailor_resume_callable",
        raise_unavailable,
    )

    with pytest.raises(ResumeTailorUnavailableError, match="unavailable"):
        tailor_resume_for_job(
            {"title": "BA", "company": "Acme", "description": "desc"},
            str(resume),
        )


def test_bridge_isolates_resume_tailor_app_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = tmp_path / "resume-tailor" / "backend"
    services = backend / "app" / "services"
    services.mkdir(parents=True, exist_ok=True)
    (backend / "app" / "__init__.py").write_text("", encoding="utf-8")
    (services / "__init__.py").write_text("", encoding="utf-8")
    (backend / "app" / "schemas.py").write_text(
        "class GenerateResponse:\n"
        "    SOURCE = 'resume-tailor'\n",
        encoding="utf-8",
    )
    (services / "tailor_pipeline.py").write_text(
        "from app.schemas import GenerateResponse\n"
        "def tailor_resume(*, resume_docx_path: str, job_description: str, context: str):\n"
        "    return {\n"
        "        'tailored_resume_sections': {'summary': [GenerateResponse.SOURCE], 'experience': []},\n"
        "        'top_alignment_highlights': [],\n"
        "        'top_gaps_to_watch': [],\n"
        "    }\n",
        encoding="utf-8",
    )

    conflicting_schemas = types.ModuleType("app.schemas")
    sys.modules["app.schemas"] = conflicting_schemas
    monkeypatch.setenv("RESUME_TAILOR_PIPELINE_PATH", str(services / "tailor_pipeline.py"))

    fn = _load_tailor_resume_callable()
    out = fn(
        resume_docx_path="resume.docx",
        job_description="desc",
        context="Target role: BA at Acme",
    )

    assert out["tailored_resume_sections"]["summary"] == ["resume-tailor"]
    assert sys.modules.get("app.schemas") is conflicting_schemas
