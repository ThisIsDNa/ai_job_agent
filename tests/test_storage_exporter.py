"""Tests for CSV export of stored jobs."""

from __future__ import annotations

import csv
from pathlib import Path

from app.schemas.job_schema import JobPostingDraft
from app.storage.exporter import export_jobs_to_csv
from app.storage.repository import update_job_status, upsert_job


def _job(url: str, title: str) -> JobPostingDraft:
    return JobPostingDraft(
        title=title,
        company="Acme",
        location="Remote",
        url=url,
        description="word " * 80,
        source="example.com",
        validation_warnings=[],
    )


def test_export_csv_creates_file(tmp_path: Path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    out_csv = str(tmp_path / "jobs_export.csv")
    upsert_job(_job("https://jobs.example.com/1", "Role 1"), db)

    exported = export_jobs_to_csv(db, out_csv)
    assert exported == 1
    assert (tmp_path / "jobs_export.csv").exists()

    with (tmp_path / "jobs_export.csv").open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["url"] == "https://jobs.example.com/1"


def test_export_csv_respects_status_filter(tmp_path: Path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    out_csv = str(tmp_path / "filtered.csv")
    upsert_job(_job("https://jobs.example.com/2", "Role 2"), db)
    upsert_job(_job("https://jobs.example.com/3", "Role 3"), db)
    update_job_status("https://jobs.example.com/3", "Interested", db)

    exported = export_jobs_to_csv(db, out_csv, status="Interested")
    assert exported == 1
    with (tmp_path / "filtered.csv").open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["url"] == "https://jobs.example.com/3"
