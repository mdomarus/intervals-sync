import unicodedata
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from .config import OPEN_PACE_ZONE_SENTINEL, RUN_TYPES
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


def format_zone_time(seconds: int) -> str:
    """Render a time-in-zone duration as M:SS (or H:MM:SS past an hour).

    Unlike a bare `seconds // 60`, this keeps the seconds so sub-minute zones read
    as "0:55" rather than the misleading "0min".
    """
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def pace_zones_table(
    pace_zone_times: list[int] | None,
    gap_zone_times: list[int] | None,
    zone_limits: list[float] | None,
    threshold_mps: float | None,
    pace_unit: PaceUnit,
) -> list[str]:
    """Build a markdown table of time-in-zone for pace and (optionally) GAP zones.

    intervals.icu `pace_zones` are the upper bound of each zone expressed as a
    percentage of the athlete's threshold pace (100% == threshold), not absolute
    speeds. The threshold itself (`threshold_mps`) is a speed in m/s, so the zone's
    upper pace bound is `threshold_mps * percent / 100`.

    Pace and GAP share the same zone bounds, so they render as one table with an
    "Up to" threshold column plus time/percent columns per series. The GAP columns
    are omitted entirely when no GAP data is present. Returns [] when there is no
    time in any zone.
    """
    if not pace_zone_times and not gap_zone_times:
        return []
    has_gap = bool(gap_zone_times)
    pace_total = sum(pace_zone_times or [])
    gap_total = sum(gap_zone_times or [])
    if pace_total == 0 and gap_total == 0:
        return []

    header = ["Zone", "Up to", "Pace time", "Pace %"]
    alignment = [":-----", "-----:", "----------:", "-------:"]
    if has_gap:
        header += ["GAP time", "GAP %"]
        alignment += ["---------:", "------:"]
    rows = [f"| {' | '.join(header)} |", f"|{'|'.join(alignment)}|"]

    zone_count = max(len(pace_zone_times or []), len(gap_zone_times or []))
    for zone_idx in range(zone_count):
        pace_time = _zone_value(pace_zone_times, zone_idx)
        gap_time = _zone_value(gap_zone_times, zone_idx)
        if pace_time == 0 and gap_time == 0:
            continue
        threshold_str = (
            _pace_zone_threshold(zone_limits, zone_idx, threshold_mps, pace_unit) or "—"
        )
        cells = [
            f"Z{zone_idx + 1}",
            threshold_str,
            *_time_and_percent(pace_time, pace_total),
        ]
        if has_gap:
            cells += _time_and_percent(gap_time, gap_total)
        rows.append(f"| {' | '.join(cells)} |")
    return rows


def _zone_value(zone_times: list[int] | None, zone_idx: int) -> int:
    if not zone_times or zone_idx >= len(zone_times):
        return 0
    return zone_times[zone_idx]


def _time_and_percent(seconds: int, total_seconds: int) -> list[str]:
    if seconds == 0 or total_seconds == 0:
        return ["—", "—"]
    return [format_zone_time(seconds), f"{round(seconds / total_seconds * 100)}%"]


def _pace_zone_threshold(
    zone_limits: list[float] | None,
    zone_idx: int,
    threshold_mps: float | None,
    pace_unit: PaceUnit,
) -> str | None:
    """Render the upper pace bound of one zone, or None when it has no bound.

    The open-ended top zone (OPEN_PACE_ZONE_SENTINEL) and missing threshold/percentage
    data both yield None so the caller drops the ``(<pace)`` suffix.
    """
    if not zone_limits or zone_idx >= len(zone_limits):
        return None
    percent_of_threshold = zone_limits[zone_idx]
    if (
        percent_of_threshold is None
        or percent_of_threshold == 0.0
        or percent_of_threshold == OPEN_PACE_ZONE_SENTINEL
        or not threshold_mps
    ):
        return None
    zone_upper_mps = threshold_mps * percent_of_threshold / 100
    return format_pace(1000, 1000 / zone_upper_mps, pace_unit)


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
