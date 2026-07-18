from datetime import date, datetime, timedelta
from typing import Any

from .formatters import (
    emoji,
    hms,
    pace,
    row,
    safe_name,
    speed_kmh,
    splits_table,
    val,
    hr_zones_summary,
)
from .state import Activity


def activity_note(
    activity: Activity,
    intervals_data: dict[str, Any] | None = None,
    weather: dict[str, Any] | None = None,
) -> str:
    activity_type = val(activity, "type", "Unknown")
    act_id = val(activity, "id", "")
    activity_emoji = emoji(activity_type)
    name = val(activity, "name", "Activity")
    start_raw = val(activity, "start_date_local", "")
    start = start_raw[:16].replace("T", " ")

    dist_m = val(activity, "distance", 0) or 0
    dist_km = round(dist_m / 1000, 2)
    moving = val(activity, "moving_time", 0) or 0
    elapsed = val(activity, "elapsed_time", 0) or 0
    elev_gain = int(val(activity, "total_elevation_gain", 0) or 0)
    elev_loss = int(val(activity, "total_elevation_loss", 0) or 0)
    alt_avg = val(activity, "average_altitude")
    alt_min = val(activity, "min_altitude")
    alt_max = val(activity, "max_altitude")

    hr_avg = val(activity, "average_heartrate")
    hr_max = val(activity, "max_heartrate")
    hr_rest = val(activity, "icu_resting_hr")
    hr_max_athlete = val(activity, "athlete_max_hr")
    lthr = val(activity, "lthr")
    zone_times = val(activity, "icu_hr_zone_times")
    zone_limits = val(activity, "icu_hr_zones")

    cadence = val(activity, "average_cadence")
    power_avg = val(activity, "icu_average_watts")
    power_weighted = val(activity, "icu_weighted_avg_watts")
    ftp = val(activity, "icu_ftp")
    intensity = val(activity, "icu_intensity")
    variability = val(activity, "icu_variability_index")
    decoupling = val(activity, "decoupling")
    ef = val(activity, "icu_efficiency_factor")
    polarization = val(activity, "polarization_index")

    ctl = val(activity, "icu_ctl")
    atl = val(activity, "icu_atl")
    training_load = val(activity, "icu_training_load")
    trimp = val(activity, "trimp")
    hr_load = val(activity, "hr_load")
    suffer = val(activity, "suffer_score")
    rpe = (
        val(activity, "icu_rpe")
        or val(activity, "session_rpe")
        or val(activity, "perceived_exertion")
    )
    feel = val(activity, "feel")

    temp_avg = val(activity, "average_temp")
    temp_min = val(activity, "min_temp")
    temp_max = val(activity, "max_temp")

    calories = val(activity, "calories")
    weight = val(activity, "icu_weight")
    device = val(activity, "device_name")
    source = val(activity, "source")
    strava_id = val(activity, "strava_id") or val(activity, "id", "")
    race = val(activity, "race", False)
    description = val(activity, "description", "") or ""
    tags = val(activity, "tags") or []
    warmup = val(activity, "icu_warmup_time")
    cooldown = val(activity, "icu_cooldown_time")
    interval_summary = val(activity, "interval_summary") or []

    tag_list = ["sport", "activity", activity_type.lower()]
    if race:
        tag_list.append("race")
    if tags:
        tag_list += tags

    pace_str = pace(dist_m, moving) if activity_type in ("Run", "TrailRun") else None
    speed_str = speed_kmh(val(activity, "average_speed"))
    max_speed_str = speed_kmh(val(activity, "max_speed"))
    zones_str = hr_zones_summary(zone_times, zone_limits)

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
        f"# {activity_emoji} {name}",
        "",
    ]
    if race:
        lines.append("> 🏁 **RACE**\n")

    lines += ["## Overview", ""]
    for note_row in filter(
        None,
        [
            row("Type", activity_type),
            row("Date", start),
            row("Distance", f"{dist_km}" if dist_km > 0 else None, "km"),
            row("Time (moving)", hms(moving) if moving else None),
            row(
                "Time (elapsed)",
                hms(elapsed) if elapsed and elapsed != moving else None,
            ),
            row("Pace", pace_str),
            row("Speed avg", speed_str, "km/h"),
            row("Speed max", max_speed_str, "km/h"),
            row("Elevation gain", elev_gain if elev_gain > 0 else None, "m"),
            row("Elevation loss", elev_loss if elev_loss > 0 else None, "m"),
            row("Warmup", hms(warmup) if warmup else None),
            row("Cooldown", hms(cooldown) if cooldown else None),
        ],
    ):
        lines.append(note_row)

    if hr_avg or hr_max:
        lines += ["", "## Heart Rate", ""]
        for note_row in filter(
            None,
            [
                row("HR avg", int(hr_avg) if hr_avg else None, "bpm"),
                row("HR max", int(hr_max) if hr_max else None, "bpm"),
                row("HR resting", hr_rest, "bpm"),
                row("HR max (athlete)", hr_max_athlete, "bpm"),
                row("LTHR", lthr, "bpm"),
            ],
        ):
            lines.append(note_row)
        if zones_str:
            lines.append(f"- **HR Zones:** {zones_str}  ")

    if power_avg or power_weighted:
        lines += ["", "## Power", ""]
        for note_row in filter(
            None,
            [
                row("Power avg", int(power_avg) if power_avg else None, "W"),
                row(
                    "Normalized Power (NP)",
                    int(power_weighted) if power_weighted else None,
                    "W",
                ),
                row("FTP", ftp, "W"),
                row(
                    "Intensity Factor", round(intensity / 100, 2) if intensity else None
                ),
                row(
                    "Variability Index", round(variability, 2) if variability else None
                ),
            ],
        ):
            lines.append(note_row)

    lines += ["", "## Training Load", ""]
    for note_row in filter(
        None,
        [
            row("Training Load", round(training_load, 1) if training_load else None),
            row("TRIMP", round(trimp, 1) if trimp else None),
            row("HR Load", round(hr_load, 1) if hr_load else None),
            row("Suffer Score", int(suffer) if suffer else None),
            row("Session Intensity", f"{round(intensity, 1)}%" if intensity else None),
            row("Efficiency Factor", round(ef, 2) if ef else None),
            row("Decoupling", f"{round(decoupling, 1)}%" if decoupling else None),
            row("Polarization Index", round(polarization, 2) if polarization else None),
            row("CTL (fitness)", round(ctl, 1) if ctl else None),
            row("ATL (fatigue)", round(atl, 1) if atl else None),
            row("TSB (freshness)", round(ctl - atl, 1) if ctl and atl else None),
        ],
    ):
        lines.append(note_row)

    if rpe or feel:
        lines += ["", "## Feel", ""]
        for note_row in filter(None, [row("RPE", rpe), row("Feel", feel)]):
            lines.append(note_row)

    if temp_avg is not None:
        lines += ["", "## Conditions", ""]
        for note_row in filter(
            None,
            [
                row("Temp avg", f"{round(temp_avg, 1)}", "°C"),
                row(
                    "Temp min/max",
                    f"{temp_min}/{temp_max}" if temp_min is not None else None,
                    "°C",
                ),
                row(
                    "Altitude avg", f"{round(alt_avg, 0):.0f}" if alt_avg else None, "m"
                ),
                row(
                    "Altitude min/max",
                    f"{alt_min:.0f}/{alt_max:.0f}" if alt_min is not None else None,
                    "m",
                ),
            ],
        ):
            lines.append(note_row)

    lines += ["", "## Other", ""]
    for note_row in filter(
        None,
        [
            row("Cadence", int(cadence) if cadence else None),
            row("Calories", int(calories) if calories else None, "kcal"),
            row("Weight", weight, "kg"),
            row("Device", device),
            row("Source", source),
        ],
    ):
        lines.append(note_row)
    if strava_id:
        lines.append(
            f"- **Strava:** [link](https://www.strava.com/activities/{strava_id})  "
        )

    if weather:
        lines += ["", "## Weather (Open-Meteo)", ""]
        for note_row in filter(
            None,
            [
                row(
                    "Temperature",
                    f"{round(weather['temp'], 1)}"
                    if weather.get("temp") is not None
                    else None,
                    "°C",
                ),
                row(
                    "Wind",
                    f"{round(weather['wind_speed'], 1)} km/h from {int(weather['wind_dir'])}°"
                    if weather.get("wind_speed") is not None
                    else None,
                ),
                row(
                    "Gusts",
                    f"{round(weather['wind_gust'], 1)}"
                    if weather.get("wind_gust") is not None
                    else None,
                    "km/h",
                ),
            ],
        ):
            lines.append(note_row)

    lines += splits_table(intervals_data, activity_type)

    if interval_summary:
        lines += ["", "## Intervals (auto-groups)", ""]
        for summary_item in interval_summary:
            lines.append(f"- {summary_item}")

    if description:
        lines += ["", "## Description", "", description]

    return "\n".join(lines)


def week_summary(activities: list[Activity], year: int, week_num: int) -> str | None:
    week_acts = []
    for activity in activities:
        date_str = activity.get("start_date_local", "")[:10]
        if not date_str:
            continue
        activity_date = datetime.strptime(date_str, "%Y-%m-%d")
        iso_calendar = activity_date.isocalendar()
        if iso_calendar[0] == year and iso_calendar[1] == week_num:
            week_acts.append(activity)
    if not week_acts:
        return None

    jan4 = date(year, 1, 4)
    week_start = jan4 + timedelta(weeks=week_num - 1, days=-jan4.weekday())
    week_end = week_start + timedelta(days=6)

    total_dist = sum((a.get("distance", 0) or 0) for a in week_acts) / 1000
    total_time = sum((a.get("moving_time", 0) or 0) for a in week_acts)
    total_elev = sum(int(a.get("total_elevation_gain", 0) or 0) for a in week_acts)
    total_load = sum((a.get("icu_training_load", 0) or 0) for a in week_acts)
    total_trimp = sum((a.get("trimp", 0) or 0) for a in week_acts)
    total_cal = sum((a.get("calories", 0) or 0) for a in week_acts)

    # CTL/ATL from the last activity of the week
    sorted_acts = sorted(
        week_acts, key=lambda activity: activity.get("start_date_local", "")
    )
    last = sorted_acts[-1]
    ctl = last.get("icu_ctl")
    atl = last.get("icu_atl")
    tsb = round(ctl - atl, 1) if ctl and atl else None

    by_type: dict[str, dict[str, Any]] = {}
    for activity in week_acts:
        activity_type = activity.get("type", "Unknown")
        by_type.setdefault(activity_type, {"count": 0, "dist": 0, "time": 0, "elev": 0})
        by_type[activity_type]["count"] += 1
        by_type[activity_type]["dist"] += (activity.get("distance", 0) or 0) / 1000
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
        f"**Period:** {week_start.strftime('%d.%m')} – {week_end.strftime('%d.%m.%Y')}",
        "",
        "## Totals",
        "",
        f"- **Activities:** {len(week_acts)}",
        f"- **Distance:** {round(total_dist, 1)} km",
        f"- **Time:** {hms(total_time)}",
        f"- **Elevation:** {total_elev} m",
    ]
    if total_load:
        lines.append(f"- **Training Load:** {round(total_load, 1)}")
    if total_trimp:
        lines.append(f"- **TRIMP:** {round(total_trimp, 1)}")
    if total_cal:
        lines.append(f"- **Calories:** {int(total_cal)} kcal")
    if ctl:
        lines.append(f"- **CTL (fitness):** {round(ctl, 1)}")
    if atl:
        lines.append(f"- **ATL (fatigue):** {round(atl, 1)}")
    if tsb is not None:
        tsb_label = "fresh 💪" if tsb > 5 else ("tired 😴" if tsb < -10 else "neutral")
        lines.append(f"- **TSB (freshness):** {tsb} ({tsb_label})")

    lines += ["", "## By type", ""]
    for activity_type, stats in sorted(by_type.items()):
        lines.append(
            f"- {emoji(activity_type)} **{activity_type}** — {stats['count']}x, "
            f"{round(stats['dist'], 1)} km, {hms(stats['time'])}, {stats['elev']} m"
        )

    lines += ["", "## Activities", ""]
    for activity in sorted_acts:
        activity_emoji = emoji(activity.get("type", ""))
        name = activity.get("name", "Activity")
        date_str = activity.get("start_date_local", "")[:10]
        dist_km = round((activity.get("distance", 0) or 0) / 1000, 1)
        training_load = activity.get("icu_training_load")
        load_str = f" | Load: {round(training_load, 1)}" if training_load else ""
        safe_note_name = safe_name(name)
        lines.append(
            f"- {activity_emoji} [[{date_str} {safe_note_name}]] — {dist_km} km{load_str}"
        )

    return "\n".join(lines)
