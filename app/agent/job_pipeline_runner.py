"""Orchestration runner for deterministic job pipeline progression."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agent.pipeline_logger import PipelineLogger
from app.agent.pipeline_states import (
    EXTRACTED,
    FAILED,
    REVIEW_READY,
    SCORED,
    TAILORED,
    is_valid_transition,
)
from app.agent.task_result import TaskResult
from app.integrations.resume_tailor_client import (
    ResumeTailorApiError,
    ResumeTailorApiUnavailableError,
    ResumeTailorClient,
)


class JobPipelineRunner:
    def __init__(self, repository, resume_tailor_client=None, db_path=None, pipeline_logger=None) -> None:
        self.repository = repository
        self.resume_tailor_client = resume_tailor_client
        self.db_path = db_path
        self.pipeline_logger = pipeline_logger or PipelineLogger()

    def _get_client(self) -> ResumeTailorClient:
        if self.resume_tailor_client is None:
            raise RuntimeError("ResumeTailorClient is required for run_to_tailored")
        return self.resume_tailor_client

    def _coerce_job_id(self, job_id: str) -> int:
        try:
            return int(str(job_id).strip())
        except ValueError as exc:
            raise ValueError("job_id must be numeric") from exc

    def _db_path_or_raise(self) -> str:
        if not self.db_path:
            raise RuntimeError("db_path is required")
        return str(self.db_path)

    def run_to_tailored(self, job_id: str) -> TaskResult:
        db_path = self._db_path_or_raise()
        job_id_int = self._coerce_job_id(job_id)
        pipeline_run_id = f"run_{uuid4().hex}"
        run_started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        self.pipeline_logger.start_run(job_id_int, pipeline_run_id)
        self.pipeline_logger.log_step(
            job_id_int,
            pipeline_run_id,
            "LOAD_JOB",
            "STARTED",
        )
        job = self.repository.get_job_by_id(job_id_int, db_path)
        if not job:
            self.pipeline_logger.log_error(
                job_id_int, pipeline_run_id, "job_not_found", f"Job not found: {job_id}", False
            )
            self.pipeline_logger.finish_run(job_id_int, pipeline_run_id, "FAILED")
            return TaskResult(
                ok=False,
                state=FAILED,
                message=f"Job not found: {job_id}",
                error_code="job_not_found",
                retryable=False,
            )
        self.pipeline_logger.log_step(job_id_int, pipeline_run_id, "LOAD_JOB", "OK")
        self.repository.update_job_pipeline_state(
            job_id_int,
            db_path,
            pipeline_state=str(job.get("pipeline_state") or EXTRACTED),
            note="Pipeline run started.",
            last_pipeline_error=None,
            pipeline_run_id=pipeline_run_id,
            set_started_at=run_started_at,
        )

        self.pipeline_logger.log_step(job_id_int, pipeline_run_id, "VALIDATE_JOB", "STARTED")
        description = str(job.get("description") or "").strip()
        if not description:
            self.repository.update_job_pipeline_state(
                job_id_int,
                db_path,
                pipeline_state=FAILED,
                note="Tailor run blocked: missing job description.",
                last_pipeline_error="missing_description",
                pipeline_run_id=pipeline_run_id,
                set_completed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            )
            self.pipeline_logger.log_error(
                job_id_int,
                pipeline_run_id,
                "missing_description",
                "Job description is missing. Cannot tailor without a description.",
                False,
            )
            self.pipeline_logger.finish_run(job_id_int, pipeline_run_id, "FAILED")
            return TaskResult(
                ok=False,
                state=FAILED,
                message="Job description is missing. Cannot tailor without a description.",
                error_code="missing_description",
                retryable=False,
            )
        self.pipeline_logger.log_step(job_id_int, pipeline_run_id, "VALIDATE_JOB", "OK")

        current_state = str(job.get("pipeline_state") or "").strip().upper() or None
        # Normalize early-stage records into a deterministic pre-tailor state.
        if current_state is None:
            self.repository.update_job_pipeline_state(
                job_id_int,
                db_path,
                pipeline_state=EXTRACTED,
                note="Pipeline initialized from legacy job record.",
                last_pipeline_error=None,
                pipeline_run_id=pipeline_run_id,
                last_successful_step="VALIDATE_JOB",
            )
            current_state = EXTRACTED
        if current_state == EXTRACTED:
            self.repository.update_job_pipeline_state(
                job_id_int,
                db_path,
                pipeline_state=SCORED,
                note="Prepared for tailoring.",
                last_pipeline_error=None,
                pipeline_run_id=pipeline_run_id,
                last_successful_step="VALIDATE_JOB",
            )
            current_state = SCORED
        if not is_valid_transition(current_state, TAILORED):
            self.pipeline_logger.log_error(
                job_id_int,
                pipeline_run_id,
                "invalid_transition",
                f"Invalid transition from {current_state} to {TAILORED}.",
                False,
            )
            self.pipeline_logger.finish_run(job_id_int, pipeline_run_id, "FAILED")
            return TaskResult(
                ok=False,
                state=current_state,
                message=f"Invalid transition from {current_state} to {TAILORED}.",
                error_code="invalid_transition",
                retryable=False,
            )

        client = self._get_client()
        self.pipeline_logger.log_step(job_id_int, pipeline_run_id, "CALL_RESUME_TAILOR", "STARTED")
        try:
            response = client.tailor_job(
                job_id=str(job_id_int),
                title=str(job.get("title") or ""),
                company=str(job.get("company") or ""),
                description=description,
                url=str(job.get("url") or ""),
            )
            self.pipeline_logger.log_step(job_id_int, pipeline_run_id, "CALL_RESUME_TAILOR", "OK")
        except ResumeTailorApiUnavailableError:
            self.repository.update_job_pipeline_state(
                job_id_int,
                db_path,
                pipeline_state=FAILED,
                note="Resume Tailor API unavailable.",
                last_pipeline_error="resume_tailor_unavailable",
                pipeline_run_id=pipeline_run_id,
                retry_count_increment=1,
                set_completed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            )
            self.pipeline_logger.log_error(
                job_id_int,
                pipeline_run_id,
                "resume_tailor_unavailable",
                "Resume Tailor API is not available.",
                True,
            )
            self.pipeline_logger.finish_run(job_id_int, pipeline_run_id, "FAILED")
            return TaskResult(
                ok=False,
                state=FAILED,
                message="Resume Tailor API is not available. Start resume-tailor backend on port 8000.",
                error_code="resume_tailor_unavailable",
                retryable=True,
                suggested_action="Start resume-tailor backend on port 8000 and retry.",
            )
        except ResumeTailorApiError as exc:
            self.repository.update_job_pipeline_state(
                job_id_int,
                db_path,
                pipeline_state=FAILED,
                note=f"Resume Tailor API error: {exc}",
                last_pipeline_error="resume_tailor_api_error",
                pipeline_run_id=pipeline_run_id,
                set_completed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            )
            self.pipeline_logger.log_error(
                job_id_int,
                pipeline_run_id,
                "resume_tailor_api_error",
                str(exc),
                False,
            )
            self.pipeline_logger.finish_run(job_id_int, pipeline_run_id, "FAILED")
            return TaskResult(
                ok=False,
                state=FAILED,
                message=str(exc),
                error_code="resume_tailor_api_error",
                retryable=False,
            )
        except Exception as exc:  # noqa: BLE001
            self.repository.update_job_pipeline_state(
                job_id_int,
                db_path,
                pipeline_state=FAILED,
                note=f"Unexpected pipeline error: {exc}",
                last_pipeline_error="unexpected_pipeline_error",
                pipeline_run_id=pipeline_run_id,
                set_completed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            )
            self.pipeline_logger.log_error(
                job_id_int,
                pipeline_run_id,
                "unexpected_pipeline_error",
                str(exc),
                True,
            )
            self.pipeline_logger.finish_run(job_id_int, pipeline_run_id, "FAILED")
            return TaskResult(
                ok=False,
                state=FAILED,
                message=f"Unexpected pipeline error: {exc}",
                error_code="unexpected_pipeline_error",
                retryable=True,
            )

        application_id = str(
            response.get("application_id")
            or response.get("id")
            or response.get("application", {}).get("application_id")
            or ""
        ).strip() or None
        fit_score_raw = response.get("fit_score")
        fit_score = int(fit_score_raw) if isinstance(fit_score_raw, (int, float)) else None
        recommended_next_step = str(response.get("recommended_next_step") or "").strip() or None
        top_gaps = response.get("top_gaps") or response.get("gap_summary") or []
        if isinstance(top_gaps, list):
            gap_summary = "; ".join(str(x) for x in top_gaps[:3] if str(x).strip()) or None
        else:
            gap_summary = str(top_gaps).strip() or None
        last_tailored_at = (
            str(response.get("tailored_at") or response.get("timestamp") or "").strip()
            or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )

        self.pipeline_logger.log_step(job_id_int, pipeline_run_id, "SAVE_RESULTS", "STARTED")
        self.repository.update_job_resume_tailor_result(
            job_id_int,
            db_path,
            application_id=application_id,
            fit_score=fit_score,
            status=recommended_next_step or "tailored",
            gap_summary=gap_summary,
            last_tailored_at=last_tailored_at,
        )
        self.pipeline_logger.log_step(job_id_int, pipeline_run_id, "SAVE_RESULTS", "OK")
        self.pipeline_logger.log_step(job_id_int, pipeline_run_id, "UPDATE_STATE", "STARTED")
        self.repository.update_job_pipeline_state(
            job_id_int,
            db_path,
            pipeline_state=TAILORED,
            note="Resume tailored via Resume Tailor API.",
            last_pipeline_error=None,
            pipeline_run_id=pipeline_run_id,
            last_successful_step="SAVE_RESULTS",
        )
        self.repository.update_job_pipeline_state(
            job_id_int,
            db_path,
            pipeline_state=REVIEW_READY,
            note="Tailored artifacts ready for review.",
            last_pipeline_error=None,
            pipeline_run_id=pipeline_run_id,
            last_successful_step="UPDATE_STATE",
            set_completed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        )
        self.pipeline_logger.log_step(job_id_int, pipeline_run_id, "UPDATE_STATE", "OK")
        self.pipeline_logger.finish_run(job_id_int, pipeline_run_id, "COMPLETED")
        return TaskResult(
            ok=True,
            state=REVIEW_READY,
            message="Job tailored successfully.",
            data={
                "pipeline_run_id": pipeline_run_id,
                "application_id": application_id,
                "fit_score": fit_score,
                "recommended_next_step": recommended_next_step,
                "top_gaps": top_gaps[:3] if isinstance(top_gaps, list) else top_gaps,
            },
        )

    def update_status(self, job_id: str, new_state: str, note: str | None = None) -> TaskResult:
        db_path = self._db_path_or_raise()
        job_id_int = self._coerce_job_id(job_id)
        job = self.repository.get_job_by_id(job_id_int, db_path)
        if not job:
            return TaskResult(
                ok=False,
                state=FAILED,
                message=f"Job not found: {job_id}",
                error_code="job_not_found",
                retryable=False,
            )
        current_state = str(job.get("pipeline_state") or "").strip().upper() or None
        target = str(new_state or "").strip().upper()
        if not is_valid_transition(current_state, target):
            return TaskResult(
                ok=False,
                state=current_state,
                message=f"Invalid transition from {current_state} to {target}.",
                error_code="invalid_transition",
                retryable=False,
            )
        updated = self.repository.update_job_pipeline_state(
            job_id_int,
            db_path,
            pipeline_state=target,
            note=note,
            last_pipeline_error=None if target != FAILED else (job.get("last_pipeline_error") or "failed"),
            last_successful_step="UPDATE_STATE",
        )
        return TaskResult(
            ok=True,
            state=target,
            message=f"Pipeline state updated to {target}.",
            data={"job_id": job_id_int, "state_history": updated.get("state_history") or []},
        )

    def get_pipeline_status(self, job_id: str) -> dict[str, Any]:
        db_path = self._db_path_or_raise()
        job_id_int = self._coerce_job_id(job_id)
        job = self.repository.get_job_by_id(job_id_int, db_path)
        if not job:
            return {
                "job_id": job_id_int,
                "pipeline_state": FAILED,
                "state_history": [],
                "last_pipeline_error": "job_not_found",
                "recent_logs": self.pipeline_logger.recent_logs(job_id_int, limit=10),
            }
        return {
            "job_id": job_id_int,
            "pipeline_state": job.get("pipeline_state"),
            "pipeline_run_id": job.get("pipeline_run_id"),
            "last_successful_step": job.get("last_successful_step"),
            "retry_count": job.get("retry_count", 0),
            "last_pipeline_started_at": job.get("last_pipeline_started_at"),
            "last_pipeline_completed_at": job.get("last_pipeline_completed_at"),
            "state_history": job.get("state_history") or [],
            "resume_tailor_application_id": job.get("resume_tailor_application_id"),
            "resume_tailor_fit_score": job.get("resume_tailor_fit_score"),
            "resume_tailor_status": job.get("resume_tailor_status"),
            "last_tailored_at": job.get("last_tailored_at"),
            "last_pipeline_error": job.get("last_pipeline_error"),
            "recent_logs": self.pipeline_logger.recent_logs(job_id_int, limit=10),
        }
