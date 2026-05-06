"""Deterministic pipeline states and transition rules for job orchestration."""

from __future__ import annotations

DISCOVERED = "DISCOVERED"
EXTRACTED = "EXTRACTED"
SCORED = "SCORED"
TAILORED = "TAILORED"
REVIEW_READY = "REVIEW_READY"
APPLIED = "APPLIED"
INTERVIEW = "INTERVIEW"
REJECTED = "REJECTED"
OFFER = "OFFER"
ARCHIVED = "ARCHIVED"
FAILED = "FAILED"

ALL_PIPELINE_STATES: tuple[str, ...] = (
    DISCOVERED,
    EXTRACTED,
    SCORED,
    TAILORED,
    REVIEW_READY,
    APPLIED,
    INTERVIEW,
    REJECTED,
    OFFER,
    ARCHIVED,
    FAILED,
)

_TERMINAL_STATES: set[str] = {REJECTED, OFFER, ARCHIVED, FAILED}

_ALLOWED_DIRECT_TRANSITIONS: set[tuple[str, str]] = {
    (DISCOVERED, EXTRACTED),
    (EXTRACTED, SCORED),
    (SCORED, TAILORED),
    (TAILORED, REVIEW_READY),
    (REVIEW_READY, APPLIED),
    (REVIEW_READY, REJECTED),
    (APPLIED, INTERVIEW),
    (APPLIED, REJECTED),
    (APPLIED, OFFER),
}


def is_valid_transition(current_state: str | None, next_state: str) -> bool:
    """Returns True when a pipeline transition is allowed by policy."""
    nxt = str(next_state or "").strip().upper()
    cur = str(current_state or "").strip().upper() if current_state else None
    if nxt not in ALL_PIPELINE_STATES:
        return False
    if cur is None:
        # Allow initializing state from an unset job.
        return nxt in {DISCOVERED, EXTRACTED, SCORED, TAILORED, REVIEW_READY, FAILED, ARCHIVED}
    if cur == nxt:
        return True
    if nxt == ARCHIVED:
        return True
    if nxt == FAILED:
        return cur not in _TERMINAL_STATES
    return (cur, nxt) in _ALLOWED_DIRECT_TRANSITIONS
