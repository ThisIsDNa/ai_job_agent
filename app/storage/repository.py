"""Repository helpers for persisting validated job drafts in SQLite."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.schemas.job_schema import JobPostingDraft
from app.storage.db import create_connection, initialize_db

ALLOWED_STATUSES: tuple[str, ...] = (
    "Found",
    "Reviewed",
    "Interested",
    "Tailor Resume",
    "Applied",
    "Rejected",
    "Archived",
)


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _row_to_dict(row: Any) -> dict:
    return dict(row) if row is not None else {}


def _decode_row(row: Any) -> dict:
    d = _row_to_dict(row)
    if not d:
        return d
    if "validation_warnings" in d and isinstance(d["validation_warnings"], str):
        try:
            d["validation_warnings"] = json.loads(d["validation_warnings"])
        except json.JSONDecodeError:
            pass
    for k in ("matched_skills", "missing_skills", "state_history"):
        if k in d and isinstance(d[k], str) and d[k]:
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
    if "state_history" in d and d.get("state_history") is None:
        d["state_history"] = []
    if "retry_count" in d and d.get("retry_count") is None:
        d["retry_count"] = 0
    return d


def _validate_status(status: str) -> str:
    s = (status or "").strip()
    if s not in ALLOWED_STATUSES:
        raise ValueError(
            f"Invalid status {status!r}. Allowed: {', '.join(ALLOWED_STATUSES)}"
        )
    return s


def upsert_job(
    job: JobPostingDraft,
    db_path: str,
    scoring: dict[str, Any] | None = None,
) -> dict:
    """Inserts new job by URL or updates existing row; returns saved row dict."""
    initialize_db(db_path)
    now = _utc_iso_now()
    warnings_json = json.dumps(list(job.validation_warnings), ensure_ascii=False)
    fit_score = None
    matched_skills_json = None
    missing_skills_json = None
    fit_reason = None
    if scoring:
        fit_score = scoring.get("fit_score")
        matched_skills_json = json.dumps(list(scoring.get("matched_skills") or []), ensure_ascii=False)
        missing_skills_json = json.dumps(list(scoring.get("missing_skills") or []), ensure_ascii=False)
        fit_reason = scoring.get("short_reason")

    with create_connection(db_path) as conn:
        existing = conn.execute("SELECT id, status, created_at FROM jobs WHERE url = ?", (job.url,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE jobs
                SET company = ?, title = ?, location = ?, description = ?, source = ?,
                    validation_warnings = ?, fit_score = ?, matched_skills = ?,
                    missing_skills = ?, fit_reason = ?, updated_at = ?
                WHERE url = ?
                """,
                (
                    job.company,
                    job.title,
                    job.location,
                    job.description,
                    job.source,
                    warnings_json,
                    fit_score,
                    matched_skills_json,
                    missing_skills_json,
                    fit_reason,
                    now,
                    job.url,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO jobs (
                    company, title, location, url, description, source, status,
                    date_found, validation_warnings, fit_score, matched_skills,
                    missing_skills, fit_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'Found', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.company,
                    job.title,
                    job.location,
                    job.url,
                    job.description,
                    job.source,
                    now,
                    warnings_json,
                    fit_score,
                    matched_skills_json,
                    missing_skills_json,
                    fit_reason,
                    now,
                    now,
                ),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM jobs WHERE url = ?", (job.url,)).fetchone()
        return _decode_row(row)


def list_jobs(db_path: str, status: str | None = None) -> list[dict]:
    """Returns saved jobs, optionally filtered by status."""
    initialize_db(db_path)
    with create_connection(db_path) as conn:
        if status is not None:
            valid = _validate_status(status)
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY updated_at DESC, id DESC",
                (valid,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY updated_at DESC, id DESC"
            ).fetchall()
    out: list[dict] = []
    for r in rows:
        out.append(_decode_row(r))
    return out


def list_jobs_for_batch(
    db_path: str,
    state_filter: str | None = None,
    min_fit_score: float | None = None,
    limit: int | None = None,
    include_archived: bool = False,
) -> list[dict]:
    """Returns candidate jobs for batch orchestration with operational filters."""
    initialize_db(db_path)
    sql = "SELECT * FROM jobs WHERE 1=1"
    params: list[Any] = []
    if state_filter is not None and str(state_filter).strip():
        sql += " AND UPPER(COALESCE(pipeline_state, '')) = ?"
        params.append(str(state_filter).strip().upper())
    if min_fit_score is not None:
        sql += " AND COALESCE(resume_tailor_fit_score, fit_score, 0) >= ?"
        params.append(float(min_fit_score))
    if not include_archived:
        sql += " AND UPPER(COALESCE(pipeline_state, '')) != 'ARCHIVED'"
        sql += " AND UPPER(COALESCE(status, '')) != 'ARCHIVED'"
    sql += " AND TRIM(COALESCE(description, '')) != ''"
    sql += " ORDER BY updated_at DESC, id DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    with create_connection(db_path) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_decode_row(r) for r in rows]


def list_review_ready_jobs(db_path: str, limit: int | None = None) -> list[dict]:
    """Returns review-ready jobs with compact review queue fields."""
    initialize_db(db_path)
    sql = """
        SELECT
            id AS job_id,
            title,
            company,
            url,
            resume_tailor_application_id,
            resume_tailor_fit_score,
            resume_tailor_status,
            resume_tailor_gap_summary,
            last_tailored_at
        FROM jobs
        WHERE UPPER(COALESCE(pipeline_state, '')) = 'REVIEW_READY'
        ORDER BY datetime(COALESCE(last_tailored_at, updated_at)) DESC, id DESC
    """
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    with create_connection(db_path) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def update_job_status(url: str, status: str, db_path: str) -> None:
    """Updates job status by URL; raises if status invalid or URL missing."""
    initialize_db(db_path)
    valid = _validate_status(status)
    now = _utc_iso_now()
    with create_connection(db_path) as conn:
        cur = conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE url = ?",
            (valid, now, url),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError(f"No job found for url {url!r}")


def get_job_by_id(job_id: int, db_path: str) -> dict | None:
    """Returns saved job row by numeric id, or None if missing."""
    initialize_db(db_path)
    with create_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return None
    return _decode_row(row)


def update_job_resume_tailor_result(
    job_id: int,
    db_path: str,
    *,
    application_id: str | None,
    fit_score: int | None,
    status: str | None,
    gap_summary: str | None,
    last_tailored_at: str,
) -> dict:
    """Updates Resume Tailor linkage fields for a saved job and returns updated row."""
    initialize_db(db_path)
    with create_connection(db_path) as conn:
        cur = conn.execute(
            """
            UPDATE jobs
            SET resume_tailor_application_id = ?,
                resume_tailor_fit_score = ?,
                resume_tailor_status = ?,
                resume_tailor_gap_summary = ?,
                last_tailored_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                application_id,
                fit_score,
                status,
                gap_summary,
                last_tailored_at,
                _utc_iso_now(),
                job_id,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError(f"No job found for id {job_id!r}")
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _decode_row(row)


def update_job_pipeline_state(
    job_id: int,
    db_path: str,
    *,
    pipeline_state: str,
    note: str | None = None,
    last_pipeline_error: str | None = None,
    pipeline_run_id: str | None = None,
    last_successful_step: str | None = None,
    retry_count_increment: int = 0,
    set_started_at: str | None = None,
    set_completed_at: str | None = None,
) -> dict:
    """Updates pipeline state and appends a state history entry."""
    initialize_db(db_path)
    now = _utc_iso_now()
    with create_connection(db_path) as conn:
        row = conn.execute(
            "SELECT state_history, retry_count FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"No job found for id {job_id!r}")
        history_raw = row["state_history"] if "state_history" in row.keys() else None
        try:
            history = json.loads(history_raw) if history_raw else []
        except json.JSONDecodeError:
            history = []
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "state": pipeline_state,
                "at": now,
                "note": note,
            }
        )
        current_retry = int(row["retry_count"] or 0) if "retry_count" in row.keys() else 0
        next_retry = current_retry + int(retry_count_increment or 0)
        conn.execute(
            """
            UPDATE jobs
            SET pipeline_state = ?,
                state_history = ?,
                last_pipeline_error = ?,
                pipeline_run_id = COALESCE(?, pipeline_run_id),
                last_successful_step = COALESCE(?, last_successful_step),
                retry_count = ?,
                last_pipeline_started_at = COALESCE(?, last_pipeline_started_at),
                last_pipeline_completed_at = COALESCE(?, last_pipeline_completed_at),
                updated_at = ?
            WHERE id = ?
            """,
            (
                pipeline_state,
                json.dumps(history, ensure_ascii=False),
                last_pipeline_error,
                pipeline_run_id,
                last_successful_step,
                next_retry,
                set_started_at,
                set_completed_at,
                now,
                job_id,
            ),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _decode_row(updated)
