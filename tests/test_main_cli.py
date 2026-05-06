"""Minimal CLI smoke tests (avoid over-testing logging)."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import patch

from app.schemas.job_schema import JobPostingDraft
from app.storage.repository import get_job_by_id, list_jobs, update_job_pipeline_state, upsert_job


def test_main_careers_url_with_debug_does_not_crash() -> None:
    fake_html = '<html><body><a href="/jobs/1">Engineer</a></body></html>'
    argv = ["prog", "--careers-url", "https://corp.example/careers", "--debug"]
    with patch.object(sys, "argv", argv):
        with patch("app.agent.agent_runner.load_page_html", return_value=fake_html):
            import main

            importlib.reload(main)
            main.main()


def test_main_job_url_with_debug_does_not_crash() -> None:
    draft = JobPostingDraft(
        title="Title",
        company="Co",
        location="Loc",
        url="https://jobs.example.com/p/1",
        description="word " * 80,
        validation_warnings=[],
    )
    argv = ["prog", "--job-url", "https://jobs.example.com/p/1", "--debug"]
    with patch.object(sys, "argv", argv):
        with patch("app.agent.agent_runner.extract_job_from_url", return_value=draft):
            import main

            importlib.reload(main)
            main.main()


def test_main_careers_url_without_debug_still_runs() -> None:
    fake_html = '<html><a href="/jobs/2">Role</a></html>'
    argv = ["prog", "--careers-url", "https://corp.example/"]
    with patch.object(sys, "argv", argv):
        with patch("app.agent.agent_runner.load_page_html", return_value=fake_html):
            import main

            importlib.reload(main)
            main.main()


def test_main_update_status_cli_path_works(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    upsert_job(
        JobPostingDraft(
            title="Role",
            company="Acme",
            location="Remote",
            url="https://jobs.example.com/cli-1",
            description="word " * 80,
            source="example.com",
            validation_warnings=[],
        ),
        db,
    )
    argv = [
        "prog",
        "--update-status",
        "https://jobs.example.com/cli-1",
        "--new-status",
        "Interested",
        "--db-path",
        db,
    ]
    with patch.object(sys, "argv", argv):
        import main

        importlib.reload(main)
        main.main()
    rows = list_jobs(db, status="Interested")
    assert len(rows) == 1
    assert rows[0]["url"] == "https://jobs.example.com/cli-1"


def test_main_update_status_invalid_status_blocked(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    upsert_job(
        JobPostingDraft(
            title="Role",
            company="Acme",
            location="Remote",
            url="https://jobs.example.com/cli-2",
            description="word " * 80,
            source="example.com",
            validation_warnings=[],
        ),
        db,
    )
    argv = [
        "prog",
        "--update-status",
        "https://jobs.example.com/cli-2",
        "--new-status",
        "NotReal",
        "--db-path",
        db,
    ]
    with patch.object(sys, "argv", argv):
        import main

        importlib.reload(main)
        try:
            main.main()
        except ValueError as exc:
            assert "Invalid status" in str(exc)
        else:
            raise AssertionError("Expected ValueError for invalid status")


def test_main_score_missing_profile_handled_safely() -> None:
    draft = JobPostingDraft(
        title="Analyst",
        company="Co",
        location="Remote",
        url="https://jobs.example.com/p/score",
        description="word " * 80,
        validation_warnings=[],
    )
    argv = [
        "prog",
        "--job-url",
        "https://jobs.example.com/p/score",
        "--score",
        "--profile-file",
        "config/does_not_exist.json",
    ]
    with patch.object(sys, "argv", argv):
        with patch("app.agent.agent_runner.extract_job_from_url", return_value=draft):
            import main

            importlib.reload(main)
            # Should not raise on missing profile file.
            main.main()


def test_main_tailor_job_updates_storage_linkage(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = upsert_job(
        JobPostingDraft(
            title="Data Analyst",
            company="Acme",
            location="Remote",
            url="https://jobs.example.com/tailor-1",
            description="SQL dashboards and reporting",
            source="example.com",
            validation_warnings=[],
        ),
        db,
    )
    argv = ["prog", "--tailor-job", str(saved["id"]), "--db-path", db]
    with patch.object(sys, "argv", argv):
        import main

        importlib.reload(main)
        with patch.object(main, "ResumeTailorClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_client.tailor_job.return_value = {
                "application_id": "app_999",
                "fit_score": 87,
                "recommended_next_step": "apply",
                "top_gaps": ["Quantify impact", "Add BI tooling keywords"],
                "tailored_at": "2026-05-05T01:00:00+00:00",
            }
            main.main()

    out = get_job_by_id(int(saved["id"]), db)
    assert out is not None
    assert out["resume_tailor_application_id"] == "app_999"
    assert out["resume_tailor_fit_score"] == 87


def test_main_tailor_job_requires_description(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = upsert_job(
        JobPostingDraft(
            title="Data Analyst",
            company="Acme",
            location="Remote",
            url="https://jobs.example.com/tailor-2",
            description=" ",
            source="example.com",
            validation_warnings=[],
        ),
        db,
    )
    argv = ["prog", "--tailor-job", str(saved["id"]), "--db-path", db]
    with patch.object(sys, "argv", argv):
        import main

        importlib.reload(main)
        try:
            main.main()
        except RuntimeError as exc:
            assert "Job description is missing" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError for missing job description")


def test_main_pipeline_logs_cli_path_works(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = upsert_job(
        JobPostingDraft(
            title="Data Analyst",
            company="Acme",
            location="Remote",
            url="https://jobs.example.com/tailor-logs",
            description="SQL dashboards and reporting",
            source="example.com",
            validation_warnings=[],
        ),
        db,
    )
    update_job_pipeline_state(
        int(saved["id"]),
        db,
        pipeline_state="EXTRACTED",
        note="seed logs",
    )
    argv = ["prog", "--pipeline-logs", str(saved["id"]), "--db-path", db]
    with patch.object(sys, "argv", argv):
        import main

        importlib.reload(main)
        main.main()


def test_main_batch_tailor_dry_run_cli_path_works(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = upsert_job(
        JobPostingDraft(
            title="Data Analyst",
            company="Acme",
            location="Remote",
            url="https://jobs.example.com/batch-1",
            description="SQL dashboards and reporting",
            source="example.com",
            validation_warnings=[],
        ),
        db,
        scoring={"fit_score": 85},
    )
    update_job_pipeline_state(
        int(saved["id"]),
        db,
        pipeline_state="SCORED",
        note="seed batch",
    )
    argv = ["prog", "--batch-tailor", "--dry-run", "--db-path", db]
    with patch.object(sys, "argv", argv):
        import main

        importlib.reload(main)
        main.main()


def test_main_review_queue_cli_path_works(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = upsert_job(
        JobPostingDraft(
            title="Data Analyst",
            company="Acme",
            location="Remote",
            url="https://jobs.example.com/review-cli",
            description="SQL dashboards and reporting",
            source="example.com",
            validation_warnings=[],
        ),
        db,
        scoring={"fit_score": 88},
    )
    from app.storage.repository import update_job_resume_tailor_result

    update_job_resume_tailor_result(
        int(saved["id"]),
        db,
        application_id="app_review_cli",
        fit_score=88,
        status="review",
        gap_summary="gap summary",
        last_tailored_at="2026-05-06T00:00:00+00:00",
    )
    update_job_pipeline_state(int(saved["id"]), db, pipeline_state="REVIEW_READY", note="seed review")
    argv = ["prog", "--review-queue", "--db-path", db, "--limit", "20"]
    with patch.object(sys, "argv", argv):
        import main

        importlib.reload(main)
        main.main()


def test_main_mark_applied_transition(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = upsert_job(
        JobPostingDraft(
            title="Data Analyst",
            company="Acme",
            location="Remote",
            url="https://jobs.example.com/mark-applied",
            description="SQL dashboards and reporting",
            source="example.com",
            validation_warnings=[],
        ),
        db,
    )
    update_job_pipeline_state(int(saved["id"]), db, pipeline_state="REVIEW_READY", note="seed")
    argv = ["prog", "--mark-applied", str(saved["id"]), "--db-path", db]
    with patch.object(sys, "argv", argv):
        import main

        importlib.reload(main)
        main.main()
    out = get_job_by_id(int(saved["id"]), db)
    assert out is not None
    assert out["pipeline_state"] == "APPLIED"


def test_main_reject_transition(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = upsert_job(
        JobPostingDraft(
            title="Data Analyst",
            company="Acme",
            location="Remote",
            url="https://jobs.example.com/reject",
            description="SQL dashboards and reporting",
            source="example.com",
            validation_warnings=[],
        ),
        db,
    )
    update_job_pipeline_state(int(saved["id"]), db, pipeline_state="REVIEW_READY", note="seed")
    argv = ["prog", "--reject-job", str(saved["id"]), "--db-path", db]
    with patch.object(sys, "argv", argv):
        import main

        importlib.reload(main)
        main.main()
    out = get_job_by_id(int(saved["id"]), db)
    assert out is not None
    assert out["pipeline_state"] == "REJECTED"


def test_main_archive_transition(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = upsert_job(
        JobPostingDraft(
            title="Data Analyst",
            company="Acme",
            location="Remote",
            url="https://jobs.example.com/archive",
            description="SQL dashboards and reporting",
            source="example.com",
            validation_warnings=[],
        ),
        db,
    )
    update_job_pipeline_state(int(saved["id"]), db, pipeline_state="SCORED", note="seed")
    argv = ["prog", "--archive-job", str(saved["id"]), "--db-path", db]
    with patch.object(sys, "argv", argv):
        import main

        importlib.reload(main)
        main.main()
    out = get_job_by_id(int(saved["id"]), db)
    assert out is not None
    assert out["pipeline_state"] == "ARCHIVED"
