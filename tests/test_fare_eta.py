from datetime import datetime, timezone
from app.core.fare_calculator import calculate_fare, is_peak_hour, BASE_FARE, RATE_PER_KM, PEAK_HOUR_MULTIPLIER
from app.core.eta import calculate_eta_minutes, AVERAGE_SPEED_KMH
from app.core.geo_utils import haversine_distance_km


class TestHaversineDistance:
    def test_same_point_is_zero_distance(self):
        """A point compared to itself must be exactly 0 — the most basic
        sanity check for any distance formula."""
        dist = haversine_distance_km(28.6139, 77.2090, 28.6139, 77.2090)
        assert dist == 0.0

    def test_known_distance_delhi_to_gurgaon(self):
        """Delhi (28.6139, 77.2090) to Gurgaon (28.4595, 77.0266) is a
        real-world straight-line distance of roughly 25 km. Testing
        against a known, verifiable real-world value rather than an
        arbitrary number — if this formula is ever swapped out, a
        wildly wrong result here (like 3km or 300km) immediately
        signals a broken implementation."""
        dist = haversine_distance_km(28.6139, 77.2090, 28.4595, 77.0266)
        assert 22 < dist < 28  # generous tolerance, still catches gross errors

    def test_distance_is_symmetric(self):
        """Distance from A to B must equal distance from B to A —
        Haversine should have no directional bias."""
        d1 = haversine_distance_km(28.6139, 77.2090, 28.4595, 77.0266)
        d2 = haversine_distance_km(28.4595, 77.0266, 28.6139, 77.2090)
        assert abs(d1 - d2) < 0.0001


class TestFareCalculation:
    def test_base_fare_at_zero_distance(self):
        """At zero distance, fare should be exactly the base fare —
        confirms the per-km term contributes nothing at distance=0."""
        off_peak_time = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)  # 2 PM, not peak
        fare = calculate_fare(0.0, at_time=off_peak_time)
        assert fare == BASE_FARE

    def test_fare_scales_linearly_with_distance(self):
        """fare = base + rate*distance — verify the formula directly,
        not just that SOME number comes out."""
        off_peak_time = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
        fare = calculate_fare(10.0, at_time=off_peak_time)
        expected = BASE_FARE + (RATE_PER_KM * 10.0)
        assert fare == round(expected, 2)

    def test_peak_hour_applies_multiplier(self):
        """8-10 AM is defined as peak — confirm the surge actually
        multiplies the fare, not just that peak hour is detected."""
        peak_time = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)  # 9 AM
        fare = calculate_fare(10.0, at_time=peak_time)
        base_fare_no_surge = BASE_FARE + (RATE_PER_KM * 10.0)
        expected = round(base_fare_no_surge * PEAK_HOUR_MULTIPLIER, 2)
        assert fare == expected

    def test_non_peak_hour_has_no_multiplier(self):
        """2 PM is explicitly NOT in either peak window — confirms the
        boundary logic doesn't accidentally apply surge everywhere."""
        off_peak_time = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
        fare = calculate_fare(10.0, at_time=off_peak_time)
        expected = round(BASE_FARE + (RATE_PER_KM * 10.0), 2)
        assert fare == expected


class TestPeakHourDetection:
    def test_morning_peak_window(self):
        assert is_peak_hour(datetime(2026, 1, 1, 8, 30, tzinfo=timezone.utc)) is True

    def test_evening_peak_window(self):
        assert is_peak_hour(datetime(2026, 1, 1, 19, 0, tzinfo=timezone.utc)) is True

    def test_midday_is_not_peak(self):
        assert is_peak_hour(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)) is False

    def test_boundary_at_10am_is_not_peak(self):
        """10 AM exactly is the END of the morning window (exclusive) —
        this catches an off-by-one error in the boundary condition."""
        assert is_peak_hour(datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)) is False


class TestETACalculation:
    def test_zero_distance_is_zero_eta(self):
        assert calculate_eta_minutes(0.0) == 0

    def test_eta_matches_speed_formula(self):
        """time = distance / speed, in minutes — verify against the
        actual constant used, so this test doesn't silently pass if
        AVERAGE_SPEED_KMH is later changed but the formula breaks."""
        distance_km = 10.0
        expected_minutes = round((distance_km / AVERAGE_SPEED_KMH) * 60)
        assert calculate_eta_minutes(distance_km) == expected_minutes

    def test_negative_distance_returns_zero(self):
        """Defensive case — should never happen in practice, but the
        function shouldn't return a negative ETA if it somehow does."""
        assert calculate_eta_minutes(-5.0) == 0
