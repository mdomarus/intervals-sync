from enum import Enum

METERS_PER_MILE = 1609.344
METERS_PER_FOOT = 0.3048
MPS_TO_MPH = 2.236936
MPS_TO_KMH = 3.6


class UnitSystem(str, Enum):
    METRIC = "METRIC"
    IMPERIAL = "IMPERIAL"


class PaceUnit(str, Enum):
    MINS_KM = "MINS_KM"
    MINS_MILE = "MINS_MILE"
    SECS_100M = "SECS_100M"
    SECS_100Y = "SECS_100Y"
    SECS_500M = "SECS_500M"
    SECS_400M = "SECS_400M"
    SECS_250M = "SECS_250M"
    NONE = "NONE"


# Reference distance (meters) and display suffix per pace unit. NONE falls back
# to per-kilometer so an unset sport still renders a sensible pace.
_PACE_REFERENCE_METERS: dict[PaceUnit, float] = {
    PaceUnit.MINS_KM: 1000.0,
    PaceUnit.MINS_MILE: METERS_PER_MILE,
    PaceUnit.SECS_100M: 100.0,
    PaceUnit.SECS_100Y: 91.44,
    PaceUnit.SECS_500M: 500.0,
    PaceUnit.SECS_400M: 400.0,
    PaceUnit.SECS_250M: 250.0,
    PaceUnit.NONE: 1000.0,
}

_PACE_SUFFIX: dict[PaceUnit, str] = {
    PaceUnit.MINS_KM: "/km",
    PaceUnit.MINS_MILE: "/mi",
    PaceUnit.SECS_100M: "/100m",
    PaceUnit.SECS_100Y: "/100y",
    PaceUnit.SECS_500M: "/500m",
    PaceUnit.SECS_400M: "/400m",
    PaceUnit.SECS_250M: "/250m",
    PaceUnit.NONE: "/km",
}


def format_distance(dist_m: float | None, system: UnitSystem) -> str | None:
    if not dist_m:
        return None
    if system is UnitSystem.IMPERIAL:
        return f"{dist_m / METERS_PER_MILE:.2f} mi"
    return f"{dist_m / 1000:.2f} km"


def format_speed(mps: float | None, system: UnitSystem) -> str | None:
    if mps is None:
        return None
    if system is UnitSystem.IMPERIAL:
        return f"{round(mps * MPS_TO_MPH, 1)} mph"
    return f"{round(mps * MPS_TO_KMH, 1)} km/h"


def format_elevation(meters: float | None, system: UnitSystem) -> str | None:
    if meters is None:
        return None
    if system is UnitSystem.IMPERIAL:
        return f"{round(meters / METERS_PER_FOOT)} ft"
    return f"{round(meters)} m"


def format_pace(
    dist_m: float | None, time_s: float | None, pace_unit: PaceUnit
) -> str | None:
    if not dist_m or not time_s:
        return None
    reference_meters = _PACE_REFERENCE_METERS[pace_unit]
    pace_secs = time_s / (dist_m / reference_meters)
    minutes, seconds = divmod(round(pace_secs), 60)
    return f"{minutes}:{seconds:02d} {_PACE_SUFFIX[pace_unit]}"
