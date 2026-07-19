from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

METERS_PER_MILE = 1609.344
METERS_PER_FOOT = 0.3048
METERS_PER_KM = 1000.0
METERS_PER_YARD = 0.9144
MPS_TO_MPH = 2.236936
MPS_TO_KMH = 3.6
KM_PER_MILE = 1.609344
KMH_TO_MPS = 3.6
KMH_TO_KNOTS = 1.852

# Upper km/h bound of each Beaufort force, index = force number. Force 12 is
# open-ended (anything above force 11's ceiling), so the list stops at 11.
_BEAUFORT_UPPER_KMH = (
    1.0,
    5.0,
    11.0,
    19.0,
    28.0,
    38.0,
    49.0,
    61.0,
    74.0,
    88.0,
    102.0,
    117.0,
)


class UnitSystem(str, Enum):
    METRIC = "METRIC"
    IMPERIAL = "IMPERIAL"


class TemperatureUnit(str, Enum):
    CELSIUS = "CELSIUS"
    FAHRENHEIT = "FAHRENHEIT"


class WindSpeedUnit(str, Enum):
    KMH = "KMH"
    MPH = "MPH"
    MPS = "MPS"
    KNOTS = "KNOTS"
    BFT = "BFT"


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


def format_temperature(celsius: float | None, unit: TemperatureUnit) -> str | None:
    if celsius is None:
        return None
    if unit is TemperatureUnit.FAHRENHEIT:
        return f"{celsius * 9 / 5 + 32:.1f} °F"
    return f"{celsius:.1f} °C"


def _beaufort_force(kmh: float) -> int:
    """Map a km/h wind speed to its Beaufort force number (0-12)."""
    for force, upper_kmh in enumerate(_BEAUFORT_UPPER_KMH):
        if kmh < upper_kmh:
            return force
    return len(_BEAUFORT_UPPER_KMH)  # force 12: above the last bounded force


def format_wind_speed(kmh: float | None, unit: WindSpeedUnit) -> str | None:
    if kmh is None:
        return None
    if unit is WindSpeedUnit.MPH:
        return f"{kmh / KM_PER_MILE:.1f} mph"
    if unit is WindSpeedUnit.MPS:
        return f"{kmh / KMH_TO_MPS:.1f} m/s"
    if unit is WindSpeedUnit.KNOTS:
        return f"{kmh / KMH_TO_KNOTS:.1f} kn"
    if unit is WindSpeedUnit.BFT:
        return f"{_beaufort_force(kmh)} Bft"
    return f"{kmh:.1f} km/h"


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
    temperature_unit: TemperatureUnit = TemperatureUnit.CELSIUS
    wind_speed_unit: WindSpeedUnit = WindSpeedUnit.KMH

    def pace_unit_for(self, activity_type: str) -> PaceUnit:
        configured = self.pace_by_type.get(activity_type)
        if configured is not None:
            return configured
        if self.system is UnitSystem.IMPERIAL:
            return PaceUnit.MINS_MILE
        return PaceUnit.MINS_KM

    @classmethod
    def from_athlete(cls, profile: Mapping[str, Any] | None) -> "UnitPreferences":
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
        temperature_unit = (
            TemperatureUnit.FAHRENHEIT
            if profile.get("fahrenheit")
            else TemperatureUnit.CELSIUS
        )
        try:
            wind_speed_unit = WindSpeedUnit(profile.get("wind_speed"))
        except ValueError:
            wind_speed_unit = WindSpeedUnit.KMH
        return cls(system, pace_by_type, temperature_unit, wind_speed_unit)
