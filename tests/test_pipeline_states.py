from __future__ import annotations

from app.agent.pipeline_states import (
    APPLIED,
    ARCHIVED,
    DISCOVERED,
    EXTRACTED,
    FAILED,
    REVIEW_READY,
    SCORED,
    TAILORED,
    is_valid_transition,
)


def test_valid_transitions() -> None:
    assert is_valid_transition(DISCOVERED, EXTRACTED)
    assert is_valid_transition(EXTRACTED, SCORED)
    assert is_valid_transition(SCORED, TAILORED)
    assert is_valid_transition(TAILORED, REVIEW_READY)
    assert is_valid_transition(REVIEW_READY, APPLIED)


def test_invalid_transition_is_blocked() -> None:
    assert not is_valid_transition(DISCOVERED, TAILORED)


def test_failed_and_archived_rules() -> None:
    assert is_valid_transition(EXTRACTED, FAILED)
    assert is_valid_transition(APPLIED, ARCHIVED)
