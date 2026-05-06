from __future__ import annotations

from app.agent.batch_logger import BatchLogger
from app.agent.batch_pipeline_runner import BatchPipelineRunner
from app.agent.task_result import TaskResult
from app.schemas.job_schema import JobPostingDraft
from app.storage import repository


class _MockJobRunner:
    def __init__(self, fail_job_ids: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self.fail_job_ids = fail_job_ids or set()

    def run_to_tailored(self, job_id: str) -> TaskResult:
        self.calls.append(job_id)
        if job_id in self.fail_job_ids:
            return TaskResult(
                ok=False,
                state="FAILED",
                message="failed mock run",
                error_code="mock_failure",
                retryable=False,
            )
        return TaskResult(
            ok=True,
            state="REVIEW_READY",
            message="ok",
            data={"application_id": f"app_{job_id}", "fit_score": 88},
        )


def _save_job(db: str, url: str, fit_score: int = 70) -> dict:
    return repository.upsert_job(
        JobPostingDraft(
            title="Analyst",
            company="Acme",
            location="Remote",
            url=url,
            description="SQL and analytics",
            source="example.com",
            validation_warnings=[],
        ),
        db,
        scoring={"fit_score": fit_score, "matched_skills": [], "missing_skills": [], "short_reason": ""},
    )


def test_batch_dry_run_returns_candidates_without_processing(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    j1 = _save_job(db, "https://jobs.example.com/1", fit_score=80)
    repository.update_job_pipeline_state(int(j1["id"]), db, pipeline_state="SCORED", note="seed")
    runner = _MockJobRunner()
    batch = BatchPipelineRunner(repository=repository, job_pipeline_runner=runner, db_path=db)
    out = batch.run_batch_to_tailored(state_filter="SCORED", dry_run=True)
    assert out["dry_run"] is True
    assert out["total_candidates"] == 1
    assert len(runner.calls) == 0


def test_batch_processes_multiple_jobs_and_continues_on_failure(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    j1 = _save_job(db, "https://jobs.example.com/2", fit_score=80)
    j2 = _save_job(db, "https://jobs.example.com/3", fit_score=81)
    repository.update_job_pipeline_state(int(j1["id"]), db, pipeline_state="SCORED", note="seed")
    repository.update_job_pipeline_state(int(j2["id"]), db, pipeline_state="SCORED", note="seed")
    runner = _MockJobRunner(fail_job_ids={str(j2["id"])})
    batch = BatchPipelineRunner(repository=repository, job_pipeline_runner=runner, db_path=db)
    out = batch.run_batch_to_tailored(state_filter="SCORED", dry_run=False, limit=10)
    assert out["processed"] == 2
    assert out["succeeded"] == 1
    assert out["failed"] == 1


def test_batch_limit_and_fit_filters_work(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    j1 = _save_job(db, "https://jobs.example.com/4", fit_score=60)
    j2 = _save_job(db, "https://jobs.example.com/5", fit_score=75)
    j3 = _save_job(db, "https://jobs.example.com/6", fit_score=90)
    for j in (j1, j2, j3):
        repository.update_job_pipeline_state(int(j["id"]), db, pipeline_state="SCORED", note="seed")
    runner = _MockJobRunner()
    batch = BatchPipelineRunner(repository=repository, job_pipeline_runner=runner, db_path=db)
    out = batch.run_batch_to_tailored(state_filter="SCORED", min_fit_score=70, limit=1, dry_run=True)
    assert out["total_candidates"] == 1
    assert out["processed"] == 1


def test_batch_summary_shape_and_logs_written(tmp_path) -> None:
    db = str(tmp_path / "jobs.sqlite")
    j1 = _save_job(db, "https://jobs.example.com/7", fit_score=88)
    repository.update_job_pipeline_state(int(j1["id"]), db, pipeline_state="SCORED", note="seed")
    runner = _MockJobRunner()
    batch = BatchPipelineRunner(repository=repository, job_pipeline_runner=runner, db_path=db)
    out = batch.run_batch_to_tailored(state_filter="SCORED", dry_run=False)
    assert str(out["batch_run_id"]).startswith("batch_")
    assert isinstance(out["results"], list)
    rows = BatchLogger().recent(out["batch_run_id"], limit=20)
    assert len(rows) > 0
