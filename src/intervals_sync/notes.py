from datetime import date, timedelta
from typing import Any

from .config import RUN_TYPES
from .formatters import (
    activity_emoji,
    format_duration,
    format_markdown_row,
    get_field,
    hr_zones_summary,
    iso_year_week,
    pace_zones_table,
    sanitize_filename,
    splits_table,
)
from .load_metrics import load_section_lines
from .state import Activity, WellnessSeries
from .units import (
    UnitPreferences,
    UnitSystem,
    format_distance,
    format_elevation,
    format_pace,
    format_speed,
)


def _distance_or_zero(dist_m: float, system: UnitSystem) -> str:
    """Distance string that renders zero as '0.00 mi' or '0.00 km' instead of vanishing.

    `format_distance` returns None for zero/absent distance (to suppress the row
    in activity notes). Weekly summaries always need a printed value, even for
    zero-distance activities — and that value must respect the active unit system.
    """
    formatted = format_distance(dist_m, system)
    if formatted is not None:
        return formatted
    return "0.00 mi" if system is UnitSystem.IMPERIAL else "0.00 km"


def activity_note(
    activity: Activity,
    prefs: UnitPreferences,
    intervals_data: dict[str, Any] | None = None,
    weather: dict[str, Any] | None = None,
) -> str:
    activity_type = get_field(activity, "type", "Unknown")
    pace_unit = prefs.pace_unit_for(activity_type)
    act_id = get_field(activity, "id", "")
    act_emoji = activity_emoji(activity_type)
    name = get_field(activity, "name", "Activity")
    start_raw = get_field(activity, "start_date_local", "")
    start = start_raw[:16].replace("T", " ")

    dist_m = get_field(activity, "distance", 0) or 0
    moving = get_field(activity, "moving_time", 0) or 0
    elapsed = get_field(activity, "elapsed_time", 0) or 0
    elev_gain = int(get_field(activity, "total_elevation_gain", 0) or 0)
    elev_loss = int(get_field(activity, "total_elevation_loss", 0) or 0)
    alt_avg = get_field(activity, "average_altitude")
    alt_min = get_field(activity, "min_altitude")
    alt_max = get_field(activity, "max_altitude")

    hr_avg = get_field(activity, "average_heartrate")
    hr_max = get_field(activity, "max_heartrate")
    hr_rest = get_field(activity, "icu_resting_hr")
    hr_max_athlete = get_field(activity, "athlete_max_hr")
    lthr = get_field(activity, "lthr")
    zone_times = get_field(activity, "icu_hr_zone_times")
    zone_limits = get_field(activity, "icu_hr_zones")

    cadence = get_field(activity, "average_cadence")
    power_avg = get_field(activity, "icu_average_watts")
    power_weighted = get_field(activity, "icu_weighted_avg_watts")
    ftp = get_field(activity, "icu_ftp")
    intensity = get_field(activity, "icu_intensity")
    variability = get_field(activity, "icu_variability_index")
    decoupling = get_field(activity, "decoupling")
    efficiency_factor = get_field(activity, "icu_efficiency_factor")
    polarization = get_field(activity, "polarization_index")

    ctl = get_field(activity, "icu_ctl")
    atl = get_field(activity, "icu_atl")
    training_load = get_field(activity, "icu_training_load")
    trimp = get_field(activity, "trimp")
    hr_load = get_field(activity, "hr_load")
    suffer = get_field(activity, "suffer_score")
    rpe = get_field(activity, "icu_rpe")
    if rpe is None:
        rpe = get_field(activity, "session_rpe")
    if rpe is None:
        rpe = get_field(activity, "perceived_exertion")
    feel = get_field(activity, "feel")

    temp_avg = get_field(activity, "average_temp")
    temp_min = get_field(activity, "min_temp")
    temp_max = get_field(activity, "max_temp")

    calories = get_field(activity, "calories")
    weight = get_field(activity, "icu_weight")
    device = get_field(activity, "device_name")
    source = get_field(activity, "source")
    strava_id = get_field(activity, "strava_id") or get_field(activity, "id", "")
    race = get_field(activity, "race", False)
    description = get_field(activity, "description", "") or ""
    tags = get_field(activity, "tags") or []
    warmup = get_field(activity, "icu_warmup_time")
    cooldown = get_field(activity, "icu_cooldown_time")
    interval_summary = get_field(activity, "interval_summary") or []

    tag_list = ["sport", "activity"]
    if activity_type != "Unknown":
        tag_list.append(activity_type.lower())
    if race:
        tag_list.append("race")
    if tags:
        tag_list += tags

    pace_str = (
        format_pace(dist_m, moving, pace_unit) if activity_type in RUN_TYPES else None
    )
    gap_mps = get_field(activity, "gap") if activity_type in RUN_TYPES else None
    gap_str = (
        format_pace(1000, 1000 / gap_mps, pace_unit)
        if gap_mps is not None and gap_mps != 0.0
        else None
    )
    threshold_mps = (
        get_field(activity, "threshold_pace") if activity_type in RUN_TYPES else None
    )
    threshold_str = (
        format_pace(1000, 1000 / threshold_mps, pace_unit)
        if threshold_mps is not None and threshold_mps != 0.0
        else None
    )
    speed_str = format_speed(get_field(activity, "average_speed"), prefs.system)
    max_speed_str = format_speed(get_field(activity, "max_speed"), prefs.system)
    zones_str = hr_zones_summary(zone_times, zone_limits)

    pace_zone_times = (
        get_field(activity, "pace_zone_times") if activity_type in RUN_TYPES else None
    )
    gap_zone_times = (
        get_field(activity, "gap_zone_times") if activity_type in RUN_TYPES else None
    )
    pace_zone_limits = (
        get_field(activity, "pace_zones") if activity_type in RUN_TYPES else None
    )
    pace_zone_rows = pace_zones_table(
        pace_zone_times, gap_zone_times, pace_zone_limits, threshold_mps, pace_unit
    )

    lines = [
        "---",
        "type: note",
        "status: active",
        f"tags: [{', '.join(tag_list)}]",
        "area: life",
        f"activity_id: {act_id}",
        f"date created: {start}",
        "---",
        "",
        f"# {act_emoji} {name}",
        "",
    ]
    if race:
        lines.append("> 🏁 **RACE**\n")

    if description:
        lines += ["## Description", "", description, ""]

    lines += ["## Overview", ""]
    lines.extend(
        filter(
            None,
            [
                format_markdown_row("Type", activity_type),
                format_markdown_row("Date", start),
                format_markdown_row("Distance", format_distance(dist_m, prefs.system)),
                format_markdown_row(
                    "Time (moving)", format_duration(moving) if moving else None
                ),
                format_markdown_row(
                    "Time (elapsed)",
                    format_duration(elapsed) if elapsed and elapsed != moving else None,
                ),
                format_markdown_row("Pace", pace_str),
                format_markdown_row("GAP", gap_str),
                format_markdown_row("Threshold", threshold_str),
                format_markdown_row("Speed avg", speed_str),
                format_markdown_row("Speed max", max_speed_str),
                format_markdown_row(
                    "Elevation gain",
                    format_elevation(elev_gain, prefs.system)
                    if elev_gain > 0
                    else None,
                ),
                format_markdown_row(
                    "Elevation loss",
                    format_elevation(elev_loss, prefs.system)
                    if elev_loss > 0
                    else None,
                ),
                format_markdown_row(
                    "Warmup", format_duration(warmup) if warmup else None
                ),
                format_markdown_row(
                    "Cooldown", format_duration(cooldown) if cooldown else None
                ),
            ],
        )
    )

    if hr_avg or hr_max:
        lines += ["", "## Heart Rate", ""]
        lines.extend(
            filter(
                None,
                [
                    format_markdown_row(
                        "HR avg", int(hr_avg) if hr_avg else None, "bpm"
                    ),
                    format_markdown_row(
                        "HR max", int(hr_max) if hr_max else None, "bpm"
                    ),
                    format_markdown_row("HR resting", hr_rest, "bpm"),
                    format_markdown_row("HR max (athlete)", hr_max_athlete, "bpm"),
                    format_markdown_row("LTHR", lthr, "bpm"),
                ],
            )
        )
        if zones_str:
            lines.append(f"- **HR Zones:** {zones_str}  ")

    if pace_zone_rows:
        lines += ["", "## Pace Zones", ""]
        lines += pace_zone_rows

    if power_avg or power_weighted:
        lines += ["", "## Power", ""]
        lines.extend(
            filter(
                None,
                [
                    format_markdown_row(
                        "Power avg", int(power_avg) if power_avg else None, "W"
                    ),
                    format_markdown_row(
                        "Normalized Power (NP)",
                        int(power_weighted) if power_weighted else None,
                        "W",
                    ),
                    format_markdown_row("FTP", ftp, "W"),
                    format_markdown_row(
                        "Intensity Factor",
                        round(intensity / 100, 2) if intensity else None,
                    ),
                    format_markdown_row(
                        "Variability Index",
                        round(variability, 2) if variability else None,
                    ),
                ],
            )
        )

    lines += ["", "## Training Load", ""]
    lines.extend(
        filter(
            None,
            [
                format_markdown_row(
                    "Training Load", round(training_load, 1) if training_load else None
                ),
                format_markdown_row("TRIMP", round(trimp, 1) if trimp else None),
                format_markdown_row("HR Load", round(hr_load, 1) if hr_load else None),
                format_markdown_row("Suffer Score", int(suffer) if suffer else None),
                format_markdown_row(
                    "Session Intensity",
                    f"{round(intensity, 1)}%" if intensity else None,
                ),
                format_markdown_row(
                    "Efficiency Factor",
                    round(efficiency_factor, 2) if efficiency_factor else None,
                ),
                format_markdown_row(
                    "Decoupling", f"{round(decoupling, 1)}%" if decoupling else None
                ),
                format_markdown_row(
                    "Polarization Index",
                    round(polarization, 2) if polarization else None,
                ),
                format_markdown_row("CTL (fitness)", round(ctl, 1) if ctl else None),
                format_markdown_row("ATL (fatigue)", round(atl, 1) if atl else None),
                format_markdown_row(
                    "TSB (freshness)",
                    round(ctl - atl, 1)
                    if ctl is not None and atl is not None
                    else None,
                ),
            ],
        )
    )

    if rpe is not None or feel is not None:
        lines += ["", "## Feel", ""]
        lines.extend(
            filter(
                None,
                [format_markdown_row("RPE", rpe), format_markdown_row("Feel", feel)],
            )
        )

    if temp_avg is not None:
        lines += ["", "## Conditions", ""]
        lines.extend(
            filter(
                None,
                [
                    format_markdown_row("Temp avg", f"{round(temp_avg, 1)}", "°C"),
                    format_markdown_row(
                        "Temp min/max",
                        f"{temp_min}/{temp_max}" if temp_min is not None else None,
                        "°C",
                    ),
                    format_markdown_row(
                        "Altitude avg",
                        format_elevation(alt_avg, prefs.system)
                        if alt_avg is not None
                        else None,
                    ),
                    format_markdown_row(
                        "Altitude min/max",
                        f"{format_elevation(alt_min, prefs.system)}/"
                        f"{format_elevation(alt_max, prefs.system)}"
                        if alt_min is not None and alt_max is not None
                        else None,
                    ),
                ],
            )
        )

    lines += ["", "## Other", ""]
    lines.extend(
        filter(
            None,
            [
                format_markdown_row("Cadence", int(cadence) if cadence else None),
                format_markdown_row(
                    "Calories", int(calories) if calories else None, "kcal"
                ),
                format_markdown_row("Weight", weight, "kg"),
                format_markdown_row("Device", device),
                format_markdown_row("Source", source),
            ],
        )
    )
    if strava_id:
        lines.append(
            f"- **Strava:** [link](https://www.strava.com/activities/{strava_id})  "
        )

    if weather:
        lines += ["", "## Weather (Open-Meteo)", ""]
        lines.extend(
            filter(
                None,
                [
                    format_markdown_row(
                        "Temperature",
                        f"{round(weather['temp'], 1)}"
                        if weather.get("temp") is not None
                        else None,
                        "°C",
                    ),
                    format_markdown_row(
                        "Wind",
                        f"{round(weather['wind_speed'], 1)} km/h from {int(weather['wind_dir'])}°"
                        if weather.get("wind_speed") is not None
                        else None,
                    ),
                    format_markdown_row(
                        "Gusts",
                        f"{round(weather['wind_gust'], 1)}"
                        if weather.get("wind_gust") is not None
                        else None,
                        "km/h",
                    ),
                ],
            )
        )

    lines += splits_table(intervals_data, activity_type, prefs)

    if interval_summary:
        lines += ["", "## Intervals (auto-groups)", ""]
        for summary_item in interval_summary:
            lines.append(f"- {summary_item}")

    return "\n".join(lines)


def week_summary(
    activities: list[Activity],
    year: int,
    week_num: int,
    prefs: UnitPreferences,
    wellness_series: WellnessSeries | None = None,
) -> str | None:
    week_acts = []
    for activity in activities:
        date_str = activity.get("start_date_local", "")[:10]
        if not date_str:
            continue
        if iso_year_week(date_str) == (year, week_num):
            week_acts.append(activity)
    if not week_acts:
        return None

    week_start = date.fromisocalendar(year, week_num, 1)  # Monday of the ISO week
    week_end = week_start + timedelta(days=6)

    total_dist_m = sum((activity.get("distance", 0) or 0) for activity in week_acts)
    total_time = sum((activity.get("moving_time", 0) or 0) for activity in week_acts)
    total_elev = sum(
        int(activity.get("total_elevation_gain", 0) or 0) for activity in week_acts
    )
    total_load = sum(
        (activity.get("icu_training_load", 0) or 0) for activity in week_acts
    )
    total_trimp = sum((activity.get("trimp", 0) or 0) for activity in week_acts)
    total_cal = sum((activity.get("calories", 0) or 0) for activity in week_acts)

    # CTL/ATL from the last activity of the week
    sorted_acts = sorted(
        week_acts, key=lambda activity: activity.get("start_date_local", "")
    )
    last = sorted_acts[-1]
    ctl = last.get("icu_ctl")
    atl = last.get("icu_atl")
    tsb = round(ctl - atl, 1) if ctl is not None and atl is not None else None

    by_type: dict[str, dict[str, Any]] = {}
    for activity in week_acts:
        activity_type = activity.get("type", "Unknown")
        by_type.setdefault(
            activity_type, {"count": 0, "dist_m": 0, "time": 0, "elev": 0}
        )
        by_type[activity_type]["count"] += 1
        by_type[activity_type]["dist_m"] += activity.get("distance", 0) or 0
        by_type[activity_type]["time"] += activity.get("moving_time", 0) or 0
        by_type[activity_type]["elev"] += int(
            activity.get("total_elevation_gain", 0) or 0
        )

    lines = [
        "---",
        "type: note",
        "status: active",
        "tags: [sport, weekly-summary]",
        "area: life",
        f"week: {year}-W{week_num:02d}",
        "---",
        "",
        f"# 📊 Weekly sport summary — {year}-W{week_num:02d}",
        f"**Period:** {week_start.strftime('%d.%m')} – {week_end.strftime('%d.%m.%Y')}",  # noqa: RUF001
        "",
        "## Totals",
        "",
        f"- **Activities:** {len(week_acts)}",
        f"- **Distance:** {_distance_or_zero(total_dist_m, prefs.system)}",
        f"- **Time:** {format_duration(total_time)}",
        f"- **Elevation:** {format_elevation(total_elev, prefs.system)}",
    ]
    if total_load:
        lines.append(f"- **Training Load:** {round(total_load, 1)}")
    if total_trimp:
        lines.append(f"- **TRIMP:** {round(total_trimp, 1)}")
    if total_cal:
        lines.append(f"- **Calories:** {int(total_cal)} kcal")
    if ctl is not None:
        lines.append(f"- **CTL (fitness):** {round(ctl, 1)}")
    if atl is not None:
        lines.append(f"- **ATL (fatigue):** {round(atl, 1)}")
    if tsb is not None:
        tsb_label = "fresh 💪" if tsb > 5 else ("tired 😴" if tsb < -10 else "neutral")
        lines.append(f"- **TSB (freshness):** {tsb} ({tsb_label})")

    lines += load_section_lines(wellness_series, year, week_num)

    lines += ["", "## By type", ""]
    for activity_type, stats in sorted(by_type.items()):
        lines.append(
            f"- {activity_emoji(activity_type)} **{activity_type}** — {stats['count']}x, "
            f"{_distance_or_zero(stats['dist_m'], prefs.system)}, "
            f"{format_duration(stats['time'])}, "
            f"{format_elevation(stats['elev'], prefs.system)}"
        )

    lines += ["", "## Activities", ""]
    for activity in sorted_acts:
        act_emoji = activity_emoji(activity.get("type", ""))
        name = activity.get("name", "Activity")
        date_str = activity.get("start_date_local", "")[:10]
        training_load = activity.get("icu_training_load")
        load_str = f" | Load: {round(training_load, 1)}" if training_load else ""
        sanitized_note_name = sanitize_filename(name)
        lines.append(
            f"- {act_emoji} [[{date_str} {sanitized_note_name}]] — "
            f"{_distance_or_zero(activity.get('distance', 0) or 0, prefs.system)}{load_str}"
        )

    return "\n".join(lines)
