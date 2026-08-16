from unittest.mock import MagicMock, patch
from app.core.matching import find_nearby_drivers, find_best_available_driver


class TestFindNearbyDrivers:
    """Tests the Redis GEOSEARCH wrapper in isolation — no real Redis
    connection, we mock what Redis WOULD return and verify our code
    calls it correctly and passes the result through unchanged."""

    @patch("app.core.matching.redis_client")
    def test_calls_geosearch_with_correct_params(self, mock_redis):
        mock_redis.geosearch.return_value = ["driver_1", "driver_2"]

        result = find_nearby_drivers(latitude=28.6139, longitude=77.2090, radius_km=5.0)

        mock_redis.geosearch.assert_called_once_with(
            "driver_locations",
            longitude=77.2090,
            latitude=28.6139,
            radius=5.0,
            unit="km",
            sort="ASC",
        )
        assert result == ["driver_1", "driver_2"]

    @patch("app.core.matching.redis_client")
    def test_no_nearby_drivers_returns_empty_list(self, mock_redis):
        mock_redis.geosearch.return_value = []
        result = find_nearby_drivers(latitude=28.6139, longitude=77.2090)
        assert result == []


class TestFindBestAvailableDriver:
    """Tests the two-step Redis-then-Postgres filter logic. Mocks BOTH
    dependencies so this test has zero external I/O — pure logic
    verification of 'does the closest AVAILABLE driver actually win.'"""

    @patch("app.core.matching.find_nearby_drivers")
    def test_returns_none_when_no_candidates(self, mock_find_nearby):
        mock_find_nearby.return_value = []
        mock_db = MagicMock()

        result = find_best_available_driver(mock_db, latitude=28.6139, longitude=77.2090)

        assert result is None
        # Should short-circuit before ever touching the DB if Redis found nobody
        mock_db.query.assert_not_called()

    @patch("app.core.matching.find_nearby_drivers")
    def test_skips_unavailable_driver_picks_next_available_one(self, mock_find_nearby):
        """This is the actual core logic being verified: candidate list
        is [driver_A, driver_B] in DISTANCE order. driver_A (closer) is
        NOT available in Postgres. driver_B (farther) IS available.
        The function must return driver_B, not driver_A, and must not
        just return the first ID blindly."""
        mock_find_nearby.return_value = ["driver_A", "driver_B"]

        mock_driver_b = MagicMock(id="driver_B")

        mock_db = MagicMock()
        # First .filter(...).first() call (checking driver_A) returns None
        # (not available); second call (checking driver_B) returns the
        # driver object (available).
        mock_query = mock_db.query.return_value
        mock_query.filter.return_value.first.side_effect = [None, mock_driver_b]

        result = find_best_available_driver(mock_db, latitude=28.6139, longitude=77.2090)

        assert result is mock_driver_b
        assert mock_query.filter.call_count == 2

    @patch("app.core.matching.find_nearby_drivers")
    def test_returns_none_when_nobody_nearby_is_available(self, mock_find_nearby):
        mock_find_nearby.return_value = ["driver_A", "driver_B"]

        mock_db = MagicMock()
        mock_query = mock_db.query.return_value
        mock_query.filter.return_value.first.side_effect = [None, None]

        result = find_best_available_driver(mock_db, latitude=28.6139, longitude=77.2090)

        assert result is None
