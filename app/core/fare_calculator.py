from datetime import datetime, timezone

# Simple, hardcoded rate structure — a real system would store this in a
# config table or pricing service, varying by city/vehicle type. Hardcoding
# here is a deliberate simplification, not an oversight.
BASE_FARE = 40.0          # flat starting charge, in currency units
RATE_PER_KM = 12.0        # charge per kilometer of distance
PEAK_HOUR_MULTIPLIER = 1.5  # basic surge — see limitation note below


def is_peak_hour(current_time: datetime) -> bool:
    """
    Extremely simplified surge trigger: flags 8-10 AM and 6-8 PM as peak.
    Real surge pricing is demand/supply-driven (ratio of open ride
    requests to available nearby drivers in a geographic cell), not a
    fixed clock schedule — this is a placeholder to demonstrate the
    concept, not a real pricing engine.
    """
    hour = current_time.hour
    return (8 <= hour < 10) or (18 <= hour < 20)


def calculate_fare(distance_km: float, at_time: datetime = None) -> float:
    """
    fare = base_fare + (rate_per_km * distance), with a flat multiplier
    applied during hardcoded 'peak' windows.

    LIMITATION, stated explicitly: real surge pricing (Uber's actual
    approach) is computed per small geographic zone, driven by the live
    ratio of ride requests to available drivers in that zone, recalculated
    continuously — not a fixed time-of-day schedule. This simplified
    version demonstrates the concept of dynamic pricing without building
    the actual demand-supply computation, which would need real-time
    aggregation across all active requests and drivers per zone.
    """
    if at_time is None:
        at_time = datetime.now(timezone.utc)

    fare = BASE_FARE + (RATE_PER_KM * distance_km)

    if is_peak_hour(at_time):
        fare *= PEAK_HOUR_MULTIPLIER

    return round(fare, 2)
