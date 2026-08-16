from app.models.trip import TripStatus
from app.core.trip_state_machine import is_valid_transition


class TestValidTransitions:
    """Every transition that SHOULD be allowed, explicitly, one per test
    — if the transition map ever changes and silently breaks one of
    these, the failure points at exactly which transition regressed."""

    def test_requested_to_ongoing(self):
        assert is_valid_transition(TripStatus.REQUESTED, TripStatus.ONGOING) is True

    def test_requested_to_cancelled(self):
        assert is_valid_transition(TripStatus.REQUESTED, TripStatus.CANCELLED) is True

    def test_ongoing_to_payment_pending(self):
        assert is_valid_transition(TripStatus.ONGOING, TripStatus.PAYMENT_PENDING) is True

    def test_ongoing_to_cancelled(self):
        assert is_valid_transition(TripStatus.ONGOING, TripStatus.CANCELLED) is True

    def test_payment_pending_to_completed(self):
        assert is_valid_transition(TripStatus.PAYMENT_PENDING, TripStatus.COMPLETED) is True


class TestInvalidTransitions:
    """The transitions that must NEVER be allowed — this is the actual
    point of having a state machine at all. Each of these represents a
    real data-corruption scenario if it were ever permitted."""

    def test_requested_cannot_skip_to_completed(self):
        """A trip can't be marked done without the ride ever happening."""
        assert is_valid_transition(TripStatus.REQUESTED, TripStatus.COMPLETED) is False

    def test_requested_cannot_skip_to_payment_pending(self):
        assert is_valid_transition(TripStatus.REQUESTED, TripStatus.PAYMENT_PENDING) is False

    def test_completed_is_terminal(self):
        """A finished trip can never transition to anything else."""
        for target in TripStatus:
            assert is_valid_transition(TripStatus.COMPLETED, target) is False

    def test_cancelled_is_terminal(self):
        """A cancelled trip can never be revived into any other status."""
        for target in TripStatus:
            assert is_valid_transition(TripStatus.CANCELLED, target) is False

    def test_ongoing_cannot_skip_to_completed(self):
        """Must go through PAYMENT_PENDING first — ride ending and
        payment settling are deliberately separate steps."""
        assert is_valid_transition(TripStatus.ONGOING, TripStatus.COMPLETED) is False

    def test_payment_pending_cannot_be_cancelled(self):
        """Once the ride has physically happened, it can't be
        'cancelled' — only completed. Cancellation only makes sense
        before or during the ride, not after it's already over."""
        assert is_valid_transition(TripStatus.PAYMENT_PENDING, TripStatus.CANCELLED) is False

    def test_ongoing_cannot_revert_to_requested(self):
        """No going backwards in the lifecycle, ever."""
        assert is_valid_transition(TripStatus.ONGOING, TripStatus.REQUESTED) is False
