# Assumed average city driving speed, in km/h. A real system would pull
# this from historical/live traffic data per road segment — this is a
# single flat constant, deliberately simplified.
AVERAGE_SPEED_KMH = 25.0


def calculate_eta_minutes(distance_km: float) -> int:
    """
    time = distance / speed, converted to minutes.

    LIMITATION: this assumes constant speed regardless of actual road
    conditions, time of day, or route complexity. A production system
    would use a routing engine's turn-by-turn estimate, informed by live
    traffic — this is a rough approximation only, and should be presented
    as such, not as a real-time-accurate prediction.
    """
    if distance_km <= 0:
        return 0
    hours = distance_km / AVERAGE_SPEED_KMH
    minutes = hours * 60
    return round(minutes)
