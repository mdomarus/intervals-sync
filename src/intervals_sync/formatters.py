import unicodedata
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from .config import RUN_TYPES
from .units import (
    PaceUnit,
    UnitPreferences,
    format_distance,
    format_pace,
    format_speed,
)


def iso_year_week(date_str: str) -> tuple[int, int]:
    """(ISO year, ISO week number) for a ``YYYY-MM-DD`` date string.

    Shared by sync (to key which weeks need regenerating) and week_summary (to
    match activities into a week) so the two can't drift on week boundaries.
    """
    parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
    iso_calendar = parsed_date.isocalendar()
    return iso_calendar[0], iso_calendar[1]


def format_duration(total_seconds: int | float | None) -> str:
    if not total_seconds:
        return "—"
    total_seconds = int(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def activity_emoji(activity_type: str) -> str:
    return {
        "Run": "🏃",
        "TrailRun": "🏔️",
        "Ride": "🚴",
        "MountainBikeRide": "🚵",
        "GravelRide": "🚵",
        "Hike": "🥾",
        "Walk": "🚶",
        "VirtualRide": "🖥️",
        "Swim": "🏊",
        "WeightTraining": "🏋️",
        "Workout": "💪",
        "NordicSki": "⛷️",
    }.get(activity_type, "🏅")


def sanitize_filename(text: str) -> str:
    def keep(c: str) -> bool:
        if c.isalnum() or c in " -_":
            return True
        cat = unicodedata.category(c)
        return cat in ("So", "Sm", "Sk", "Sc")

    return "".join(char if keep(char) else "_" for char in text)


def get_field(activity: Mapping[str, Any], key: str, default: Any = None) -> Any:
    value = activity.get(key)
    return default if value is None else value


def format_markdown_row(label: str, value: Any, unit: str = "") -> str | None:
    if value is None or value == "" or value == "—":
        return None
    return f"- **{label}:** {value}{(' ' + unit) if unit else ''}  "


def hr_zones_summary(
    zone_times: list[int] | None, zone_limits: list[int] | None
) -> str | None:
    if not zone_times or not zone_limits:
        return None
    total = sum(zone_times)
    if total == 0:
        return None
    parts = []
    for zone_idx, (zone_time, zone_limit) in enumerate(
        zip(zone_times, zone_limits, strict=False)
    ):
        if zone_time > 0:
            pct = round(zone_time / total * 100)
            mins = zone_time // 60
            parts.append(f"Z{zone_idx + 1} ({zone_limit}+bpm): {mins}min ({pct}%)")
    return " | ".join(parts)


def pace_zones_summary(
    zone_times: list[int] | None,
    zone_limits: list[float] | None,
    pace_unit: PaceUnit,
) -> str | None:
    if not zone_times:
        return None
    total = sum(zone_times)
    if total == 0:
        return None
    parts = []
    for zone_idx, zone_time in enumerate(zone_times):
        if zone_time == 0:
            continue
        pct = round(zone_time / total * 100)
        mins = zone_time // 60
        if (
            zone_limits
            and zone_idx < len(zone_limits)
            and zone_limits[zone_idx] is not None
            and zone_limits[zone_idx] != 0.0
        ):
            threshold_str = (
                format_pace(1000, 1000 / zone_limits[zone_idx], pace_unit) or "?"
            )
            label = f"Z{zone_idx + 1} (<{threshold_str})"
        else:
            label = f"Z{zone_idx + 1}"
        parts.append(f"{label}: {mins}min ({pct}%)")
    return " | ".join(parts)


def splits_table(
    intervals_data: dict[str, Any] | None,
    activity_type: str,
    prefs: UnitPreferences,
) -> list[str]:
    """Build a splits table from the /intervals response."""
    if not intervals_data:
        return []
    raw_intervals = intervals_data.get("icu_intervals") or []
    if not raw_intervals:
        return []
    is_run = activity_type in RUN_TYPES
    pace_unit = prefs.pace_unit_for(activity_type)
    lines: list[str] = ["", "## Splits (intervals.icu)", ""]
    if is_run:
        hdr = (
            "| # | Type | Distance | Time | Pace | GAP | HR avg | HR max | Zone | Int |"
        )
        sep = "|--:|:---|--------:|-----:|------:|----:|-------:|-------:|-----:|----:|"
    else:
        hdr = "| # | Type | Distance | Time | Speed | HR avg | HR max | Zone | Int |"
        sep = "|--:|:---|--------:|-----:|------:|-------:|-------:|-----:|----:|"
    lines.append(hdr)
    lines.append(sep)
    for idx, interval in enumerate(raw_intervals, 1):
        interval_type = interval.get("type", "")
        type_label = (
            "🟢 WORK"
            if interval_type == "WORK"
            else ("⚪ REC" if interval_type == "RECOVERY" else interval_type)
        )
        dist = interval.get("distance", 0) or 0
        moving_time = interval.get("moving_time", 0) or 0
        hr_avg = (
            int(interval["average_heartrate"])
            if interval.get("average_heartrate")
            else "—"
        )
        hr_max = (
            int(interval["max_heartrate"]) if interval.get("max_heartrate") else "—"
        )
        zone = interval.get("zone") or "—"
        intensity = (
            f"{int(interval['intensity'])}%" if interval.get("intensity") else "—"
        )
        dist_str = format_distance(dist, prefs.system) or "—"
        time_str = format_duration(moving_time) if moving_time else "—"
        if is_run:
            pace_str = format_pace(dist, moving_time, pace_unit) or "—"
            gap_mps = interval.get("gap")
            gap_str = format_pace(1000, 1000 / gap_mps, pace_unit) if gap_mps else "—"
            table_row = f"| {idx} | {type_label} | {dist_str} | {time_str} | {pace_str} | {gap_str} | {hr_avg} | {hr_max} | Z{zone} | {intensity} |"
        else:
            speed_str = format_speed(interval.get("average_speed"), prefs.system) or "—"
            table_row = f"| {idx} | {type_label} | {dist_str} | {time_str} | {speed_str} | {hr_avg} | {hr_max} | Z{zone} | {intensity} |"
        lines.append(table_row)
    return lines
