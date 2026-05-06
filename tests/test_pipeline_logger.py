from __future__ import annotations

from app.agent.pipeline_logger import PipelineLogger


def test_pipeline_logger_appends_and_reads_recent_logs(tmp_path) -> None:
    logger = PipelineLogger(tmp_path / "pipeline_logs")
    logger.start_run(1, "run_1")
    logger.log_step(1, "run_1", "LOAD_JOB", "OK", {"title": "Analyst"})
    logger.log_error(1, "run_1", "network_error", "service down", True)
    logger.finish_run(1, "run_1", "FAILED")

    rows = logger.recent_logs(1, limit=10)
    assert len(rows) >= 4
    assert rows[0]["pipeline_run_id"] == "run_1"
    assert any(r.get("step_name") == "ERROR" for r in rows)
