"""Agent orchestration: careers discovery and single-job extraction."""

from __future__ import annotations

from typing import Any

from app.extract.job_link_finder import find_job_links
from app.extract.page_loader import load_page_html
from app.parse.job_parser import parse_job_page
from app.score.fit_scorer import score_job_fit
from app.schemas.job_schema import JobPostingDraft
from app.validation.validator import validate_job_posting_draft


def discover_jobs_from_careers_page(
    careers_url: str,
    *,
    debug: bool = False,
    trace: dict[str, Any] | None = None,
) -> list[dict]:
    """
    Loads a careers page, returns candidate job link dicts (title, url, source).

    Flow: extract (HTML) -> find links. No validation of individual jobs here.
    """
    html = load_page_html(careers_url, debug=debug)
    if trace is not None:
        trace["requested_url"] = careers_url
        trace["html_char_len"] = len(html)
    link_stats: dict[str, Any] | None = {} if trace is not None else None
    links = find_job_links(careers_url, html, stats=link_stats)
    if trace is not None and link_stats is not None:
        trace["link_stats"] = link_stats
    return links


def extract_job_from_url(
    job_url: str,
    *,
    debug: bool = False,
    trace: dict[str, Any] | None = None,
    profile: dict | None = None,
) -> JobPostingDraft:
    """
    Loads a job page, parses draft fields, validates (blocking gate), returns draft.

    Flow: extract -> parse -> validate.
    """
    html = load_page_html(job_url, debug=debug)
    if trace is not None:
        trace["requested_url"] = job_url
        trace["html_char_len"] = len(html)
    parsed = parse_job_page(job_url, html)
    if trace is not None:
        trace["parsed_title"] = parsed.get("title")
        trace["parsed_company"] = parsed.get("company")
        trace["parsed_location"] = parsed.get("location")
        desc = parsed.get("description") or ""
        trace["description_len_before_validation"] = len(str(desc))
    draft = validate_job_posting_draft(parsed)
    if trace is not None:
        trace["validation_warnings"] = list(draft.validation_warnings)
        if profile:
            trace["fit_scoring"] = score_job_fit(draft, profile)
    return draft


def run_agent() -> None:
    """Legacy no-op entry; use CLI in main.py for the MVP slice."""
    # TODO: optional interactive agent loop when requirements stabilize.
