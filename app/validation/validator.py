"""Blocking validation for job posting drafts (validation-first gate)."""

from __future__ import annotations

from urllib.parse import urlparse

from app.schemas.job_schema import JobPostingDraft

# Meaningful JD text (heuristic; blocks empty boilerplate pages).
# Shared with parse layer for thin-SSR merge threshold — keep in sync conceptually.
MIN_JOB_DESCRIPTION_CHARS = 100


def validate_job_posting_draft(data: dict) -> JobPostingDraft:
    """
    Validates parsed dict; raises ValueError on blocking failures.

    Non-blocking gaps become validation_warnings on the returned model.
    Does not silently repair malformed fields.
    """
    warnings: list[str] = []

    url = data.get("url")
    if url is None or not str(url).strip():
        raise ValueError("Blocking validation failed: url is required")
    url = str(url).strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Blocking validation failed: invalid url: {url!r}")

    desc = data.get("description")
    if desc is None:
        raise ValueError("Blocking validation failed: description is required")
    if not str(desc).strip():
        raise ValueError("Blocking validation failed: description is empty")
    description = str(desc).strip()
    if len(description) < MIN_JOB_DESCRIPTION_CHARS:
        raise ValueError(
            "Blocking validation failed: description is too short "
            f"(min {MIN_JOB_DESCRIPTION_CHARS} chars, got {len(description)})"
        )

    title = data.get("title")
    title_s = str(title).strip() if title is not None else ""
    if not title_s:
        warnings.append("missing title")
        title_out: str | None = None
    else:
        title_out = title_s

    company = data.get("company")
    company_s = str(company).strip() if company is not None else ""
    if not company_s:
        warnings.append("missing company")
        company_out: str | None = None
    else:
        company_out = company_s

    location = data.get("location")
    loc_s = str(location).strip() if location is not None else ""
    if not loc_s:
        warnings.append("missing location")
        location_out: str | None = None
    else:
        location_out = loc_s

    source = data.get("source")
    source_out = str(source).strip() if source is not None and str(source).strip() else None

    return JobPostingDraft(
        title=title_out,
        company=company_out,
        location=location_out,
        url=url,
        description=description,
        source=source_out,
        validation_warnings=warnings,
    )
