from dataclasses import dataclass
from enum import Enum
from typing import Any

METERS_PER_MILE = 1609.344
METERS_PER_FOOT = 0.3048
METERS_PER_KM = 1000.0
METERS_PER_YARD = 0.9144
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
    PaceUnit.MINS_KM: METERS_PER_KM,
    PaceUnit.MINS_MILE: METERS_PER_MILE,
    PaceUnit.SECS_100M: 100.0,
    PaceUnit.SECS_100Y: 100 * METERS_PER_YARD,
    PaceUnit.SECS_500M: 500.0,
    PaceUnit.SECS_400M: 400.0,
    PaceUnit.SECS_250M: 250.0,
    PaceUnit.NONE: METERS_PER_KM,
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
    return f"{dist_m / METERS_PER_KM:.2f} km"


def format_speed(mps: float | None, system: UnitSystem) -> str | None:
    if mps is None:
        return None
    if system is UnitSystem.IMPERIAL:
        return f"{mps * MPS_TO_MPH:.1f} mph"
    return f"{mps * MPS_TO_KMH:.1f} km/h"


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


@dataclass(frozen=True)
class UnitPreferences:
    """Athlete-configured units, resolved from the intervals.icu profile."""

    system: UnitSystem
    pace_by_type: dict[str, PaceUnit]

    def pace_unit_for(self, activity_type: str) -> PaceUnit:
        configured = self.pace_by_type.get(activity_type)
        if configured is not None:
            return configured
        if self.system is UnitSystem.IMPERIAL:
            return PaceUnit.MINS_MILE
        return PaceUnit.MINS_KM

    @classmethod
    def from_athlete(cls, profile: dict[str, Any] | None) -> "UnitPreferences":
        if not profile:
            return cls(UnitSystem.METRIC, {})
        raw_preference = str(profile.get("measurement_preference", "")).upper()
        system = (
            UnitSystem.IMPERIAL
            if raw_preference == UnitSystem.IMPERIAL.value
            else UnitSystem.METRIC
        )
        pace_by_type: dict[str, PaceUnit] = {}
        for sport_setting in profile.get("sportSettings") or []:
            raw_pace = sport_setting.get("pace_units")
            try:
                pace_unit = PaceUnit(raw_pace)
            except ValueError:
                continue
            for activity_type in sport_setting.get("types") or []:
                pace_by_type[activity_type] = pace_unit
        return cls(system, pace_by_type)
