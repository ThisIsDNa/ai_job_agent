from __future__ import annotations

from app.agent.job_pipeline_runner import JobPipelineRunner
from app.agent.pipeline_logger import PipelineLogger
from app.agent.pipeline_states import EXTRACTED, FAILED, REVIEW_READY, SCORED
from app.integrations.resume_tailor_client import ResumeTailorApiUnavailableError
from app.schemas.job_schema import JobPostingDraft
from app.storage import repository


class _MockClient:
    def __init__(self, response: dict | None = None, fail_unavailable: bool = False) -> None:
        self.response = response or {}
        self.fail_unavailable = fail_unavailable

    def tailor_job(self, **kwargs):  # type: ignore[no-untyped-def]
        if self.fail_unavailable:
            raise ResumeTailorApiUnavailableError("down")
        return self.response


def _save_job(db: str, *, description: str = "SQL and analytics") -> dict:
    return repository.upsert_job(
        JobPostingDraft(
            title="Analyst",
            company="Acme",
            location="Remote",
            url="https://jobs.example.com/pipeline",
            description=description,
            source="example.com",
            validation_warnings=[],
        ),
        db,
    )


def _runner(tmp_path, db: str, client: _MockClient) -> JobPipelineRunner:
    return JobPipelineRunner(
        repository=repository,
        resume_tailor_client=client,
        db_path=db,
        pipeline_logger=PipelineLogger(tmp_path / "pipeline_logs"),
    )


def test_run_to_tailored_success(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = _save_job(db)
    repository.update_job_pipeline_state(
        int(saved["id"]), db, pipeline_state=EXTRACTED, note="seed"
    )
    runner = _runner(
        tmp_path,
        db,
        _MockClient(
            {
                "application_id": "app_1",
                "fit_score": 90,
                "recommended_next_step": "apply",
                "top_gaps": ["gap a"],
            }
        ),
    )
    result = runner.run_to_tailored(str(saved["id"]))
    assert result.ok is True
    assert result.state == REVIEW_READY
    assert str(result.data.get("pipeline_run_id") or "").startswith("run_")
    status = runner.get_pipeline_status(str(saved["id"]))
    assert status["resume_tailor_application_id"] == "app_1"
    assert status["pipeline_state"] == REVIEW_READY
    assert str(status["pipeline_run_id"]).startswith("run_")
    assert status["last_successful_step"] == "UPDATE_STATE"
    assert isinstance(status.get("recent_logs"), list)
    assert len(status["recent_logs"]) > 0


def test_run_to_tailored_missing_job(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    runner = _runner(tmp_path, db, _MockClient({}))
    result = runner.run_to_tailored("999")
    assert result.ok is False
    assert result.error_code == "job_not_found"


def test_run_to_tailored_missing_description(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = _save_job(db, description=" ")
    runner = _runner(tmp_path, db, _MockClient({}))
    result = runner.run_to_tailored(str(saved["id"]))
    assert result.ok is False
    assert result.error_code == "missing_description"
    assert result.state == FAILED
    status = runner.get_pipeline_status(str(saved["id"]))
    assert status["retry_count"] == 0


def test_run_to_tailored_resume_tailor_unavailable(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = _save_job(db)
    repository.update_job_pipeline_state(
        int(saved["id"]), db, pipeline_state=SCORED, note="seed"
    )
    runner = _runner(tmp_path, db, _MockClient(fail_unavailable=True))
    result = runner.run_to_tailored(str(saved["id"]))
    assert result.ok is False
    assert result.retryable is True
    assert result.error_code == "resume_tailor_unavailable"
    status = runner.get_pipeline_status(str(saved["id"]))
    assert status["retry_count"] == 1
    recent = status.get("recent_logs") or []
    assert any(str(r.get("step_name")) == "ERROR" for r in recent)


def test_update_status_valid_transition(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = _save_job(db)
    repository.update_job_pipeline_state(
        int(saved["id"]), db, pipeline_state=EXTRACTED, note="seed"
    )
    runner = _runner(tmp_path, db, _MockClient({}))
    result = runner.update_status(str(saved["id"]), SCORED, note="progressed")
    assert result.ok is True
    assert result.state == SCORED


def test_update_status_invalid_transition(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = _save_job(db)
    repository.update_job_pipeline_state(
        int(saved["id"]), db, pipeline_state=EXTRACTED, note="seed"
    )
    runner = _runner(tmp_path, db, _MockClient({}))
    result = runner.update_status(str(saved["id"]), REVIEW_READY)
    assert result.ok is False
    assert result.error_code == "invalid_transition"


def test_pipeline_status_output_contains_expected_fields(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    saved = _save_job(db)
    repository.update_job_resume_tailor_result(
        int(saved["id"]),
        db,
        application_id="app_2",
        fit_score=77,
        status="review",
        gap_summary="gap",
        last_tailored_at="2026-05-05T00:00:00+00:00",
    )
    repository.update_job_pipeline_state(
        int(saved["id"]), db, pipeline_state=REVIEW_READY, note="done"
    )
    runner = _runner(tmp_path, db, _MockClient({}))
    status = runner.get_pipeline_status(str(saved["id"]))
    assert status["pipeline_state"] == REVIEW_READY
    assert status["resume_tailor_application_id"] == "app_2"
    assert status["resume_tailor_fit_score"] == 77
    assert isinstance(status["state_history"], list)
    assert "last_successful_step" in status
    assert "retry_count" in status
