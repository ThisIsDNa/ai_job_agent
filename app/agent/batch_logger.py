"""Append-only batch orchestration logs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class BatchLogger:
    def __init__(self, logs_dir: str | Path = "data/pipeline_logs/batches") -> None:
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _path(self, batch_run_id: str) -> Path:
        return self.logs_dir / f"{batch_run_id}.jsonl"

    def append(
        self,
        *,
        batch_run_id: str,
        event: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        row = {
            "timestamp": self._now(),
            "batch_run_id": batch_run_id,
            "event": event,
            "status": status,
            "details": details or {},
        }
        with self._path(batch_run_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def recent(self, batch_run_id: str, limit: int = 50) -> list[dict[str, Any]]:
        p = self._path(batch_run_id)
        if not p.exists():
            return []
        rows: list[dict[str, Any]] = []
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows[-max(1, int(limit)) :]
