"""Batch orchestration for processing multiple jobs safely."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.agent.batch_logger import BatchLogger
from app.agent.job_pipeline_runner import JobPipelineRunner


class BatchPipelineRunner:
    def __init__(self, repository, job_pipeline_runner=None, db_path=None) -> None:
        self.repository = repository
        self.job_pipeline_runner: JobPipelineRunner | None = job_pipeline_runner
        self.db_path = db_path
        self.batch_logger = BatchLogger()

    def _db_path_or_raise(self) -> str:
        if not self.db_path:
            raise RuntimeError("db_path is required")
        return str(self.db_path)

    def run_batch_to_tailored(
        self,
        state_filter: str | None = "SCORED",
        min_fit_score: float | None = None,
        limit: int | None = 10,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        db_path = self._db_path_or_raise()
        batch_run_id = f"batch_{uuid4().hex}"
        self.batch_logger.append(
            batch_run_id=batch_run_id,
            event="BATCH_STARTED",
            status="STARTED",
            details={
                "state_filter": state_filter,
                "min_fit_score": min_fit_score,
                "limit": limit,
                "dry_run": dry_run,
            },
        )

        candidates = self.repository.list_jobs_for_batch(
            db_path,
            state_filter=state_filter,
            min_fit_score=min_fit_score,
            limit=limit,
            include_archived=False,
        )
        results: list[dict[str, Any]] = []
        for job in candidates:
            self.batch_logger.append(
                batch_run_id=batch_run_id,
                event="CANDIDATE_SELECTED",
                status="OK",
                details={
                    "job_id": job.get("id"),
                    "title": job.get("title"),
                    "company": job.get("company"),
                },
            )
            if dry_run:
                results.append(
                    {
                        "job_id": str(job.get("id")),
                        "title": str(job.get("title") or ""),
                        "company": str(job.get("company") or ""),
                        "ok": True,
                        "pipeline_state": str(job.get("pipeline_state") or ""),
                        "resume_tailor_application_id": job.get("resume_tailor_application_id"),
                        "fit_score": job.get("resume_tailor_fit_score") or job.get("fit_score"),
                        "error_code": None,
                        "message": "Dry run candidate.",
                    }
                )
                continue

            if self.job_pipeline_runner is None:
                raise RuntimeError("job_pipeline_runner is required when dry_run is false")

            tr = self.job_pipeline_runner.run_to_tailored(str(job.get("id")))
            if tr.ok:
                self.batch_logger.append(
                    batch_run_id=batch_run_id,
                    event="JOB_PROCESSED",
                    status="OK",
                    details={
                        "job_id": job.get("id"),
                        "state": tr.state,
                        "application_id": tr.data.get("application_id"),
                    },
                )
            else:
                self.batch_logger.append(
                    batch_run_id=batch_run_id,
                    event="JOB_FAILED",
                    status="FAILED",
                    details={
                        "job_id": job.get("id"),
                        "error_code": tr.error_code,
                        "message": tr.message,
                    },
                )

            results.append(
                {
                    "job_id": str(job.get("id")),
                    "title": str(job.get("title") or ""),
                    "company": str(job.get("company") or ""),
                    "ok": bool(tr.ok),
                    "pipeline_state": tr.state,
                    "resume_tailor_application_id": tr.data.get("application_id"),
                    "fit_score": tr.data.get("fit_score") or job.get("fit_score"),
                    "error_code": tr.error_code,
                    "message": tr.message,
                }
            )

        processed = len(results)
        succeeded = len([r for r in results if r.get("ok")])
        failed = processed - succeeded
        summary = {
            "batch_run_id": batch_run_id,
            "dry_run": bool(dry_run),
            "state_filter": state_filter,
            "min_fit_score": min_fit_score,
            "limit": limit,
            "total_candidates": len(candidates),
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        }
        self.batch_logger.append(
            batch_run_id=batch_run_id,
            event="BATCH_COMPLETED",
            status="COMPLETED",
            details={
                "processed": processed,
                "succeeded": succeeded,
                "failed": failed,
            },
        )
        return summary
