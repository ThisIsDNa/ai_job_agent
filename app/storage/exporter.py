"""CSV export utilities for persisted jobs."""

from __future__ import annotations

import csv
from pathlib import Path

from app.storage.repository import list_jobs


def export_jobs_to_csv(db_path: str, output_path: str, status: str | None = None) -> int:
    """
    Export jobs from SQLite to CSV.

    Returns the number of exported job rows.
    """
    rows = list_jobs(db_path, status=status)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "company",
        "title",
        "location",
        "url",
        "status",
        "date_found",
        "validation_warnings",
        "updated_at",
    ]
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) for k in columns})
    return len(rows)
