"""SQLite schema statements for local storage entities."""

from __future__ import annotations

JOBS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT,
    title TEXT,
    location TEXT,
    url TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'Found',
    date_found TEXT NOT NULL,
    validation_warnings TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fit_score INTEGER,
    matched_skills TEXT,
    missing_skills TEXT,
    fit_reason TEXT
);
"""

JOBS_OPTIONAL_COLUMNS: dict[str, str] = {
    "fit_score": "INTEGER",
    "matched_skills": "TEXT",
    "missing_skills": "TEXT",
    "fit_reason": "TEXT",
    "resume_tailor_application_id": "TEXT",
    "resume_tailor_fit_score": "INTEGER",
    "resume_tailor_status": "TEXT",
    "resume_tailor_gap_summary": "TEXT",
    "last_tailored_at": "TEXT",
    "pipeline_state": "TEXT",
    "state_history": "TEXT",
    "last_pipeline_error": "TEXT",
    "pipeline_run_id": "TEXT",
    "last_successful_step": "TEXT",
    "retry_count": "INTEGER",
    "last_pipeline_started_at": "TEXT",
    "last_pipeline_completed_at": "TEXT",
}

