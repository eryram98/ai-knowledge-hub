# backend/app/ingestion/constants.py
"""
Shared constants and state transition rules for ingestion pipeline lifecycle.
Compatible with Python 3.6.
"""

from typing import Dict, FrozenSet

# Canonical lifecycle states (must stay aligned with PRD/UI contract)
INGESTION_STATUS_QUEUED = "queued"
INGESTION_STATUS_PROCESSING = "processing"
INGESTION_STATUS_SUCCESS = "success"
INGESTION_STATUS_FAILED = "failed"

INGESTION_STATUSES = (
    INGESTION_STATUS_QUEUED,
    INGESTION_STATUS_PROCESSING,
    INGESTION_STATUS_SUCCESS,
    INGESTION_STATUS_FAILED,
)

TERMINAL_INGESTION_STATUSES = (
    INGESTION_STATUS_SUCCESS,
    INGESTION_STATUS_FAILED,
)

# Allowed status transitions:
# queued -> processing | failed
# processing -> success | failed
# success -> (terminal)
# failed -> (terminal)
ALLOWED_STATUS_TRANSITIONS = {
    INGESTION_STATUS_QUEUED: frozenset(
        [INGESTION_STATUS_PROCESSING, INGESTION_STATUS_FAILED]
    ),  # type: Dict[str, FrozenSet[str]]
    INGESTION_STATUS_PROCESSING: frozenset(
        [INGESTION_STATUS_SUCCESS, INGESTION_STATUS_FAILED]
    ),
    INGESTION_STATUS_SUCCESS: frozenset([]),
    INGESTION_STATUS_FAILED: frozenset([]),
}


def is_valid_ingestion_status(status):
    # type: (str) -> bool
    """Return True when status is one of the canonical ingestion statuses."""
    return status in INGESTION_STATUSES


def can_transition_ingestion_status(current_status, next_status):
    # type: (str, str) -> bool
    """
    Return True if current_status can legally transition to next_status.
    Invalid/unknown statuses are treated as non-transitionable.
    """
    if not is_valid_ingestion_status(current_status):
        return False
    if not is_valid_ingestion_status(next_status):
        return False

    allowed_next = ALLOWED_STATUS_TRANSITIONS.get(current_status, frozenset())
    return next_status in allowed_next
