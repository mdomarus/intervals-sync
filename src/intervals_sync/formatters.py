import unicodedata
from datetime import datetime
from typing import Any, Mapping

from .config import RUN_TYPES


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


def format_pace(dist_m: float | None, time_s: float | None) -> str | None:
    if not dist_m or not time_s:
        return None
    pace_secs_per_km = time_s / (dist_m / 1000)
    minutes, seconds = divmod(int(pace_secs_per_km), 60)
    return f"{minutes}:{seconds:02d} /km"


def mps_to_kmh(mps: float | None) -> float | None:
    if not mps:
        return None
    return round(mps * 3.6, 1)


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

    return "".join(c if keep(c) else "_" for c in text)


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
    for zone_idx, (zone_time, zone_limit) in enumerate(zip(zone_times, zone_limits)):
        if zone_time > 0:
            pct = round(zone_time / total * 100)
            mins = zone_time // 60
            parts.append(f"Z{zone_idx + 1} ({zone_limit}+bpm): {mins}min ({pct}%)")
    return " | ".join(parts)


def splits_table(
    intervals_data: dict[str, Any] | None, activity_type: str
) -> list[str]:
    """Build a splits table from the /intervals response."""
    if not intervals_data:
        return []
    raw_intervals = intervals_data.get("icu_intervals") or []
    if not raw_intervals:
        return []
    is_run = activity_type in RUN_TYPES
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
        dist_str = f"{dist / 1000:.2f} km" if dist else "—"
        time_str = format_duration(moving_time) if moving_time else "—"
        if is_run:
            pace_str = format_pace(dist, moving_time) or "—"
            gap_mps = interval.get("gap")
            gap_str = format_pace(1000, 1000 / gap_mps) if gap_mps else "—"
            table_row = f"| {idx} | {type_label} | {dist_str} | {time_str} | {pace_str} | {gap_str} | {hr_avg} | {hr_max} | Z{zone} | {intensity} |"
        else:
            speed = mps_to_kmh(interval.get("average_speed"))
            speed_str = f"{speed} km/h" if speed else "—"
            table_row = f"| {idx} | {type_label} | {dist_str} | {time_str} | {speed_str} | {hr_avg} | {hr_max} | Z{zone} | {intensity} |"
        lines.append(table_row)
    return lines
