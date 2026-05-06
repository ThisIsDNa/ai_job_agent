"""Tests for local SQLite storage repository behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.job_schema import JobPostingDraft
from app.storage.db import create_connection, initialize_db
from app.storage.repository import (
    get_job_by_id,
    list_review_ready_jobs,
    list_jobs_for_batch,
    list_jobs,
    update_job_resume_tailor_result,
    upsert_job,
    update_job_status,
)


def _mk_job(url: str, title: str = "Engineer", company: str = "Acme") -> JobPostingDraft:
    return JobPostingDraft(
        title=title,
        company=company,
        location="Remote",
        url=url,
        description="word " * 80,
        source="example.com",
        validation_warnings=["missing location"] if title == "NoLoc" else [],
    )


def test_initialize_db_creates_jobs_table(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"
    initialize_db(str(db))
    with create_connection(str(db)) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
        ).fetchone()
    assert row is not None
    assert row["name"] == "jobs"


def test_upsert_inserts_new_job(tmp_path: Path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    out = upsert_job(_mk_job("https://jobs.example.com/1"), db)
    assert out["id"] is not None
    assert out["url"] == "https://jobs.example.com/1"
    assert out["status"] == "Found"


def test_upsert_updates_existing_job_by_url(tmp_path: Path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    first = upsert_job(_mk_job("https://jobs.example.com/2", title="Old"), db)
    second = upsert_job(_mk_job("https://jobs.example.com/2", title="New"), db)
    assert first["id"] == second["id"]
    assert second["title"] == "New"
    rows = list_jobs(db)
    assert len([r for r in rows if r["url"] == "https://jobs.example.com/2"]) == 1


def test_list_jobs_returns_saved_rows(tmp_path: Path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    upsert_job(_mk_job("https://jobs.example.com/3"), db)
    upsert_job(_mk_job("https://jobs.example.com/4"), db)
    rows = list_jobs(db)
    urls = {r["url"] for r in rows}
    assert "https://jobs.example.com/3" in urls
    assert "https://jobs.example.com/4" in urls


def test_update_job_status_changes_status(tmp_path: Path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    upsert_job(_mk_job("https://jobs.example.com/5"), db)
    update_job_status("https://jobs.example.com/5", "Interested", db)
    rows = list_jobs(db, status="Interested")
    assert len(rows) == 1
    assert rows[0]["url"] == "https://jobs.example.com/5"


def test_invalid_status_is_blocked(tmp_path: Path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    upsert_job(_mk_job("https://jobs.example.com/6"), db)
    with pytest.raises(ValueError, match="Invalid status"):
        update_job_status("https://jobs.example.com/6", "NotAStatus", db)


def test_upsert_with_scoring_metadata_saves_fields(tmp_path: Path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    scoring = {
        "fit_score": 78,
        "matched_skills": ["SQL", "Excel"],
        "missing_skills": ["Power BI"],
        "short_reason": "Matched 2/3 core skills; role_match=yes; years_hint=aligned",
    }
    out = upsert_job(_mk_job("https://jobs.example.com/7"), db, scoring=scoring)
    assert out["fit_score"] == 78
    assert out["matched_skills"] == ["SQL", "Excel"]
    assert out["missing_skills"] == ["Power BI"]
    assert "Matched 2/3" in str(out["fit_reason"])


def test_upsert_without_scoring_still_works(tmp_path: Path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    out = upsert_job(_mk_job("https://jobs.example.com/8"), db)
    assert out["url"] == "https://jobs.example.com/8"
    assert out.get("fit_score") is None


def test_resume_tailor_fields_are_saved_on_job_record(tmp_path: Path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = upsert_job(_mk_job("https://jobs.example.com/rt-1"), db)
    updated = update_job_resume_tailor_result(
        int(saved["id"]),
        db,
        application_id="app_777",
        fit_score=91,
        status="apply",
        gap_summary="Add SQL metric depth",
        last_tailored_at="2026-05-05T00:00:00+00:00",
    )
    assert updated["resume_tailor_application_id"] == "app_777"
    assert updated["resume_tailor_fit_score"] == 91
    assert updated["resume_tailor_status"] == "apply"
    assert updated["resume_tailor_gap_summary"] == "Add SQL metric depth"
    fetched = get_job_by_id(int(saved["id"]), db)
    assert fetched is not None
    assert fetched["resume_tailor_application_id"] == "app_777"


def test_list_jobs_for_batch_filters_state_fit_and_limit(tmp_path: Path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    a = upsert_job(_mk_job("https://jobs.example.com/b1"), db, scoring={"fit_score": 50})
    b = upsert_job(_mk_job("https://jobs.example.com/b2"), db, scoring={"fit_score": 80})
    c = upsert_job(_mk_job("https://jobs.example.com/b3"), db, scoring={"fit_score": 90})
    from app.storage.repository import update_job_pipeline_state

    update_job_pipeline_state(int(a["id"]), db, pipeline_state="SCORED", note="seed")
    update_job_pipeline_state(int(b["id"]), db, pipeline_state="SCORED", note="seed")
    update_job_pipeline_state(int(c["id"]), db, pipeline_state="EXTRACTED", note="seed")
    rows = list_jobs_for_batch(db, state_filter="SCORED", min_fit_score=70, limit=1)
    assert len(rows) == 1
    assert rows[0]["url"] == "https://jobs.example.com/b2"


def test_list_review_ready_jobs_returns_expected_shape(tmp_path: Path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    out = upsert_job(_mk_job("https://jobs.example.com/review-1"), db, scoring={"fit_score": 84})
    from app.storage.repository import update_job_pipeline_state

    update_job_resume_tailor_result(
        int(out["id"]),
        db,
        application_id="app_review_1",
        fit_score=84,
        status="review",
        gap_summary="Quantify impact; add leadership example",
        last_tailored_at="2026-05-06T00:00:00+00:00",
    )
    update_job_pipeline_state(int(out["id"]), db, pipeline_state="REVIEW_READY", note="ready")
    rows = list_review_ready_jobs(db, limit=20)
    assert len(rows) == 1
    row = rows[0]
    assert row["job_id"] == out["id"]
    assert row["resume_tailor_application_id"] == "app_review_1"
    assert "title" in row and "company" in row and "url" in row
