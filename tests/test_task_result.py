from __future__ import annotations

from app.agent.task_result import TaskResult


def test_task_result_shape_defaults() -> None:
    result = TaskResult(ok=True, state="TAILORED", message="done")
    assert result.ok is True
    assert result.state == "TAILORED"
    assert result.message == "done"
    assert result.data == {}
    assert result.error_code is None
    assert result.retryable is False
    assert result.suggested_action is None
