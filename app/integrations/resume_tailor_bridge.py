"""Thin, reversible bridge to Resume Tailor callable entry point."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any, Callable


class ResumeTailorUnavailableError(RuntimeError):
    """Raised when Resume Tailor callable entry point cannot be resolved/imported."""


_PIPELINE_ENV = "RESUME_TAILOR_PIPELINE_PATH"


def _default_tailor_pipeline_path() -> Path:
    # ai_job_agent/app/integrations/resume_tailor_bridge.py
    # -> ai_job_agent (parents[2]) -> sibling resume-tailor/backend/app/services/tailor_pipeline.py
    here = Path(__file__).resolve()
    ai_job_agent_root = here.parents[2]
    return ai_job_agent_root.parent / "resume-tailor" / "backend" / "app" / "services" / "tailor_pipeline.py"


def _resolve_tailor_pipeline_path() -> Path:
    override = (os.environ.get(_PIPELINE_ENV) or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _default_tailor_pipeline_path().resolve()


def _load_tailor_resume_callable() -> Callable[..., Any]:
    path = _resolve_tailor_pipeline_path()
    if not path.exists():
        raise ResumeTailorUnavailableError(
            f"Resume Tailor pipeline not found at {path}. "
            f"Set {_PIPELINE_ENV} to override."
        )

    backend_root = path.parents[2]
    original_sys_path = list(sys.path)
    # Both repos use top-level "app". Isolate import so Resume Tailor "app" wins here.
    original_app_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "app" or name.startswith("app.")
    }

    try:
        sys.path.insert(0, str(backend_root))
        for name in list(sys.modules):
            if name == "app" or name.startswith("app."):
                sys.modules.pop(name, None)

        module = importlib.import_module("app.services.tailor_pipeline")
        fn = getattr(module, "tailor_resume", None)
        if not callable(fn):
            raise ResumeTailorUnavailableError(
                f"Expected callable tailor_resume in {path}, but it was not found."
            )
        return fn
    except ResumeTailorUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ResumeTailorUnavailableError(
            f"Unable to import Resume Tailor callable from {path}: {exc}"
        ) from exc
    finally:
        sys.path[:] = original_sys_path
        for name in list(sys.modules):
            if name == "app" or name.startswith("app."):
                sys.modules.pop(name, None)
        sys.modules.update(original_app_modules)


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def tailor_resume_for_job(job: dict, resume_path: str) -> dict:
    """
    Bridge contract for Resume Tailor integration.

    Accepts job context + base resume path, calls Resume Tailor callable entry point,
    and normalizes output into preview shape used by this UI.
    """
    p = Path(resume_path)
    if not p.exists():
        raise FileNotFoundError(f"Base resume not found: {resume_path}")

    title = str(job.get("title") or "").strip() or "Target Role"
    company = str(job.get("company") or "").strip() or "Target Company"
    description = str(job.get("description") or "").strip()
    context = f"Target role: {title} at {company}"

    try:
        tailor_resume = _load_tailor_resume_callable()
        result = tailor_resume(
            resume_docx_path=str(p),
            job_description=description,
            context=context,
        )
    except ResumeTailorUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Resume Tailor call failed: {exc}") from exc

    # Normalize GenerateResponse-like object / dict to UI preview shape.
    if hasattr(result, "model_dump"):
        payload = result.model_dump()  # pydantic model
    elif isinstance(result, dict):
        payload = result
    else:
        payload = dict(getattr(result, "__dict__", {}) or {})

    sections = payload.get("tailored_resume_sections") or {}
    summary_lines = _as_list(sections.get("summary"))
    tailored_summary = (
        str(summary_lines[0]).strip()
        if summary_lines and str(summary_lines[0]).strip()
        else str(payload.get("tailored_resume_text") or "").strip().splitlines()[0]
        if str(payload.get("tailored_resume_text") or "").strip()
        else ""
    )
    updated_experience = [str(x).strip() for x in _as_list(sections.get("experience")) if str(x).strip()]
    if not updated_experience:
        updated_experience = [
            str(x.get("after") or "").strip()
            for x in _as_list(payload.get("prioritized_bullet_changes"))
            if isinstance(x, dict) and str(x.get("after") or "").strip()
        ]

    top_align = [str(x) for x in _as_list(payload.get("top_alignment_highlights")) if str(x).strip()]
    gaps = [str(x) for x in _as_list(payload.get("top_gaps_to_watch")) if str(x).strip()]
    notes = [
        "Bridge mode: using Resume Tailor callable entry point.",
        f"Base resume: {p.name}",
    ]
    if top_align:
        notes.append(f"Top alignment highlights: {top_align[:3]}")
    if gaps:
        notes.append(f"Top gaps to watch: {gaps[:3]}")

    return {
        "tailored_summary": tailored_summary,
        "updated_experience": updated_experience,
        "notes": notes,
    }

