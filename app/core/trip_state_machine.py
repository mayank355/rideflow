from app.models.trip import TripStatus

# Defines which transitions are legal. Anything not listed here is
# forbidden — a trip can never jump straight from REQUESTED to COMPLETED
# (skipping the actual ride), and COMPLETED/CANCELLED are terminal states
# with no valid transitions out of them at all.
VALID_TRANSITIONS = {
    TripStatus.REQUESTED: {TripStatus.ONGOING, TripStatus.CANCELLED},
    TripStatus.ONGOING: {TripStatus.COMPLETED, TripStatus.CANCELLED},
    TripStatus.COMPLETED: set(),   # terminal — no transitions out
    TripStatus.CANCELLED: set(),   # terminal — no transitions out
}


def is_valid_transition(current_status: TripStatus, new_status: TripStatus) -> bool:
    """
    A trip's status is a state machine, not a free-form field. This
    function is the single source of truth for what's allowed — without
    it, a naive update endpoint would let a COMPLETED trip silently
    become ONGOING again, or let a trip skip straight from REQUESTED to
    COMPLETED without the ride ever happening. Both are data corruption,
    not just "unusual" states.
    """
    allowed_next_states = VALID_TRANSITIONS.get(current_status, set())
    return new_status in allowed_next_states
