"""Append-only structured execution logs for orchestration runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PipelineLogger:
    def __init__(self, logs_dir: str | Path = "data/pipeline_logs") -> None:
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _log_path(self, job_id: str | int) -> Path:
        return self.logs_dir / f"job_{job_id}.jsonl"

    def _append(self, entry: dict[str, Any]) -> None:
        path = self._log_path(entry["job_id"])
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def start_run(self, job_id, pipeline_run_id) -> None:  # type: ignore[no-untyped-def]
        self.log_step(job_id, pipeline_run_id, "STARTED", "STARTED")

    def log_step(  # type: ignore[no-untyped-def]
        self,
        job_id,
        pipeline_run_id,
        step_name,
        status,
        details=None,
    ) -> None:
        self._append(
            {
                "timestamp": self._now(),
                "job_id": str(job_id),
                "pipeline_run_id": str(pipeline_run_id),
                "step_name": str(step_name),
                "status": str(status),
                "details": details or {},
            }
        )

    def finish_run(self, job_id, pipeline_run_id, status) -> None:  # type: ignore[no-untyped-def]
        self.log_step(job_id, pipeline_run_id, "COMPLETED", status)

    def log_error(  # type: ignore[no-untyped-def]
        self,
        job_id,
        pipeline_run_id,
        error_code,
        message,
        retryable,
    ) -> None:
        self._append(
            {
                "timestamp": self._now(),
                "job_id": str(job_id),
                "pipeline_run_id": str(pipeline_run_id),
                "step_name": "ERROR",
                "status": "FAILED",
                "error_code": str(error_code),
                "message": str(message),
                "retryable": bool(retryable),
                "details": {},
            }
        )

    def recent_logs(self, job_id: str | int, limit: int = 20) -> list[dict[str, Any]]:
        path = self._log_path(job_id)
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows[-max(1, int(limit)) :]
