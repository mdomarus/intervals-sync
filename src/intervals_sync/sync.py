import json
import os
import sys
import time
import urllib.error
import urllib.request
import base64
import glob
import re
from typing import Any, Mapping, cast
from datetime import datetime, timedelta, date
from .weather import fetch_weather
from .state import load_state, save_state, State, Activity


def _load_secrets() -> tuple[str, str, str, str]:
    """Load athlete_id + api_key from gitignored secrets.json next to the script
    (fallback: env vars INTERVALS_ATHLETE_ID / INTERVALS_API_KEY, INTERVALS_VAULT_PATH)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets.json")
    if os.path.exists(path):
        with open(path) as f:
            secrets = json.load(f)
        return (
            secrets["athlete_id"],
            secrets["api_key"],
            secrets["activities_dir"],
            secrets["weekly_dir"],
        )
    return (
        os.environ["INTERVALS_ATHLETE_ID"],
        os.environ["INTERVALS_API_KEY"],
        os.environ["INTERVALS_ACTIVITIES_DIR"],
        os.environ["INTERVALS_WEEKLY_DIR"],
    )


INTERVALS_API_URL = "https://intervals.icu/api/v1"
ATHLETE_ID, API_KEY, ACTIVITIES_DIR, WEEKLY_DIR = _load_secrets()
DEFAULT_LAT, DEFAULT_LON = (
    54.5189,
    18.5305,
)  # Gdynia — fallback when activity has no GPS


def write_text_safe(
    path: str, content: str, retries: int = 4, delay: float = 1.5
) -> bool:
    """Atomic, iCloud-safe file write.

    Writes to a temp file in the same directory and swaps it via os.replace()
    (atomic rename). This bypasses the iCloud File Provider lock that plain
    open(path, "w") hits as EPERM when the file is mid-sync — that was the
    cause of 07:00 failures. Retries on transient OSError. Returns True/False
    (False = failed to save; caller decides whether to continue).
    """
    parent_dir = os.path.dirname(path)
    os.makedirs(parent_dir, exist_ok=True)
    tmp = os.path.join(parent_dir, f".{os.path.basename(path)}.tmp.{os.getpid()}")
    last = None
    for attempt in range(retries):
        try:
            with open(tmp, "w") as f:
                f.write(content)
            os.replace(tmp, path)
            return True
        except OSError as e:
            last = e
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    print(f"  ⚠️  failed to save {os.path.basename(path)}: {last}")
    return False


def get_creds() -> str:
    return base64.b64encode(f"API_KEY:{API_KEY}".encode()).decode()


def get_headers() -> dict[str, str]:
    return {
        "Authorization": f"Basic {get_creds()}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 intervals-sync",
    }


def api_get(path: str) -> Any:
    url = f"{INTERVALS_API_URL}/athlete/{ATHLETE_ID}/{path}"
    req = urllib.request.Request(
        url,
        headers=get_headers(),
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def get_activity(act_id: str) -> dict | None:
    """Fetch a fresh single activity record (e.g. after server-side settings change)."""
    try:
        url = f"{INTERVALS_API_URL}/activity/{act_id}"
        req = urllib.request.Request(
            url,
            headers=get_headers(),
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  ⚠️  activity refetch failed for {act_id}: {e}")
        return None


def set_elevation_correction(act_id: str, value: bool) -> bool:
    """Enable/disable elevation correction (DEM) on intervals.icu. Disabled = device
    barometer — consistent with Strava/Garmin. Returns True on success. After PUT the
    server recalculates total_elevation_gain asynchronously."""
    try:
        url = f"{INTERVALS_API_URL}/activity/{act_id}"
        data = json.dumps({"use_elevation_correction": value}).encode()
        req = urllib.request.Request(
            url,
            data=data,
            method="PUT",
            headers={**get_headers(), "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"  ⚠️  failed to set elevation_correction for {act_id}: {e}")
        return False


def hms(total_seconds: int | float | None) -> str:
    if not total_seconds:
        return "—"
    total_seconds = int(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def pace(dist_m: float | None, time_s: float | None) -> str | None:
    if not dist_m or not time_s:
        return None
    pace_secs_per_km = time_s / (dist_m / 1000)
    minutes, seconds = divmod(int(pace_secs_per_km), 60)
    return f"{minutes}:{seconds:02d} /km"


def speed_kmh(mps: float | None) -> float | None:
    if not mps:
        return None
    return round(mps * 3.6, 1)


def emoji(t: str) -> str:
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
    }.get(t, "🏅")


def safe_name(text: str) -> str:
    import unicodedata

    def keep(c):
        if c.isalnum() or c in " -_":
            return True
        cat = unicodedata.category(c)
        return cat in ("So", "Sm", "Sk", "Sc")  # emoji and Unicode symbols

    return "".join(c if keep(c) else "_" for c in text)


def scan_existing_notes() -> dict[str, str]:
    """Map of {activity_id: relpath} read from frontmatter of existing notes.

    Disk is the source of truth for rename detection and collision avoidance —
    the ID lives in the note itself (activity_id:), so we don't rely on an
    external state file that may drift or be unaware of pre-tracking notes."""
    out = {}
    for note_path in glob.glob(f"{ACTIVITIES_DIR}/**/*.md", recursive=True):
        try:
            with open(note_path) as f:
                head = f.read(800)
        except OSError:
            continue
        match = re.search(r"(?m)^activity_id:\s*(\S+)\s*$", head)
        if match:
            out[match.group(1)] = os.path.relpath(note_path, ACTIVITIES_DIR)
    return out


def val(a: Mapping, key: str, default=None):
    value = a.get(key)
    return default if value is None else value


def row(label: str, value, unit: str = "") -> str | None:
    if value is None or value == "" or value == "—":
        return None
    return f"- **{label}:** {value}{(' ' + unit) if unit else ''}  "


def hr_zones_summary(zone_times: list | None, zone_limits: list | None) -> str | None:
    if not zone_times or not zone_limits:
        return None
    total = sum(zone_times)
    if total == 0:
        return None
    labels = ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]
    parts = []
    for zone_idx, (zone_time, zone_limit) in enumerate(zip(zone_times, zone_limits)):
        if zone_time > 0:
            pct = round(zone_time / total * 100)
            mins = zone_time // 60
            parts.append(f"{labels[zone_idx]} ({zone_limit}+bpm): {mins}min ({pct}%)")
    return " | ".join(parts)


def fetch_intervals(act_id: str) -> dict | None:
    """Fetch detailed splits (WORK/RECOVERY) for an activity."""
    try:
        url = f"{INTERVALS_API_URL}/activity/{act_id}/intervals"
        req = urllib.request.Request(
            url,
            headers=get_headers(),
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  ⚠️  intervals fetch failed for {act_id}: {e}")
        return None


def splits_table(intervals_data: dict | None, atype: str) -> list[str]:
    """Build a splits table from the /intervals response."""
    if not intervals_data:
        return []
    ivs = intervals_data.get("icu_intervals") or []
    if not ivs:
        return []
    is_run = atype in ("Run", "TrailRun")
    lines = ["", "## Splits (intervals.icu)", ""]
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
    for idx, iv in enumerate(ivs, 1):
        interval_type = iv.get("type", "")
        type_label = (
            "🟢 WORK"
            if interval_type == "WORK"
            else ("⚪ REC" if interval_type == "RECOVERY" else interval_type)
        )
        dist = iv.get("distance", 0) or 0
        moving_time = iv.get("moving_time", 0) or 0
        hr_avg = int(iv["average_heartrate"]) if iv.get("average_heartrate") else "—"
        hr_max = int(iv["max_heartrate"]) if iv.get("max_heartrate") else "—"
        zone = iv.get("zone") or "—"
        intensity = f"{int(iv['intensity'])}%" if iv.get("intensity") else "—"
        dist_str = f"{dist / 1000:.2f} km" if dist else "—"
        time_str = hms(moving_time) if moving_time else "—"
        if is_run:
            pace_str = pace(dist, moving_time) or "—"
            gap_mps = iv.get("gap")
            gap_str = pace(1000, 1000 / gap_mps) if gap_mps else "—"
            table_row = f"| {idx} | {type_label} | {dist_str} | {time_str} | {pace_str} | {gap_str} | {hr_avg} | {hr_max} | Z{zone} | {intensity} |"
        else:
            speed = speed_kmh(iv.get("average_speed"))
            speed_str = f"{speed} km/h" if speed else "—"
            table_row = f"| {idx} | {type_label} | {dist_str} | {time_str} | {speed_str} | {hr_avg} | {hr_max} | Z{zone} | {intensity} |"
        lines.append(table_row)
    return lines


def activity_note(
    a: Activity, intervals_data: dict | None = None, weather: dict | None = None
) -> str:
    atype = val(a, "type", "Unknown")
    act_id = val(a, "id", "")
    activity_emoji = emoji(atype)
    name = val(a, "name", "Activity")
    start_raw = val(a, "start_date_local", "")
    start = start_raw[:16].replace("T", " ")

    dist_m = val(a, "distance", 0) or 0
    dist_km = round(dist_m / 1000, 2)
    moving = val(a, "moving_time", 0) or 0
    elapsed = val(a, "elapsed_time", 0) or 0
    elev_gain = int(val(a, "total_elevation_gain", 0) or 0)
    elev_loss = int(val(a, "total_elevation_loss", 0) or 0)
    alt_avg = val(a, "average_altitude")
    alt_min = val(a, "min_altitude")
    alt_max = val(a, "max_altitude")

    hr_avg = val(a, "average_heartrate")
    hr_max = val(a, "max_heartrate")
    hr_rest = val(a, "icu_resting_hr")
    hr_max_athlete = val(a, "athlete_max_hr")
    lthr = val(a, "lthr")
    zone_times = val(a, "icu_hr_zone_times")
    zone_limits = val(a, "icu_hr_zones")

    cadence = val(a, "average_cadence")
    power_avg = val(a, "icu_average_watts")
    power_weighted = val(a, "icu_weighted_avg_watts")
    ftp = val(a, "icu_ftp")
    intensity = val(a, "icu_intensity")
    variability = val(a, "icu_variability_index")
    decoupling = val(a, "decoupling")
    ef = val(a, "icu_efficiency_factor")
    polarization = val(a, "polarization_index")

    ctl = val(a, "icu_ctl")
    atl = val(a, "icu_atl")
    training_load = val(a, "icu_training_load")
    trimp = val(a, "trimp")
    hr_load = val(a, "hr_load")
    suffer = val(a, "suffer_score")
    rpe = val(a, "icu_rpe") or val(a, "session_rpe") or val(a, "perceived_exertion")
    feel = val(a, "feel")

    temp_avg = val(a, "average_temp")
    temp_min = val(a, "min_temp")
    temp_max = val(a, "max_temp")

    calories = val(a, "calories")
    weight = val(a, "icu_weight")
    device = val(a, "device_name")
    source = val(a, "source")
    strava_id = val(a, "strava_id") or val(a, "id", "")
    race = val(a, "race", False)
    description = val(a, "description", "") or ""
    tags = val(a, "tags") or []
    warmup = val(a, "icu_warmup_time")
    cooldown = val(a, "icu_cooldown_time")
    interval_summary = val(a, "interval_summary") or []

    tag_list = ["sport", "activity", atype.lower()]
    if race:
        tag_list.append("race")
    if tags:
        tag_list += tags

    pace_str = pace(dist_m, moving) if atype in ("Run", "TrailRun") else None
    speed_str = speed_kmh(val(a, "average_speed"))
    max_speed_str = speed_kmh(val(a, "max_speed"))
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
    for r in filter(
        None,
        [
            row("Type", atype),
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
        lines.append(r)

    if hr_avg or hr_max:
        lines += ["", "## Heart Rate", ""]
        for r in filter(
            None,
            [
                row("HR avg", int(hr_avg) if hr_avg else None, "bpm"),
                row("HR max", int(hr_max) if hr_max else None, "bpm"),
                row("HR resting", hr_rest, "bpm"),
                row("HR max (athlete)", hr_max_athlete, "bpm"),
                row("LTHR", lthr, "bpm"),
            ],
        ):
            lines.append(r)
        if zones_str:
            lines.append(f"- **HR Zones:** {zones_str}  ")

    if power_avg or power_weighted:
        lines += ["", "## Power", ""]
        for r in filter(
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
            lines.append(r)

    lines += ["", "## Training Load", ""]
    for r in filter(
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
        lines.append(r)

    if rpe or feel:
        lines += ["", "## Feel", ""]
        for r in filter(
            None,
            [
                row("RPE", rpe),
                row("Feel", feel),
            ],
        ):
            lines.append(r)

    if temp_avg is not None:
        lines += ["", "## Conditions", ""]
        for r in filter(
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
            lines.append(r)

    lines += ["", "## Other", ""]
    for r in filter(
        None,
        [
            row("Cadence", int(cadence) if cadence else None),
            row("Calories", int(calories) if calories else None, "kcal"),
            row("Weight", weight, "kg"),
            row("Device", device),
            row("Source", source),
        ],
    ):
        lines.append(r)
    if strava_id:
        lines.append(
            f"- **Strava:** [link](https://www.strava.com/activities/{strava_id})  "
        )

    if weather:
        lines += ["", "## Weather (Open-Meteo)", ""]
        for r in filter(
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
            lines.append(r)

    lines += splits_table(intervals_data, atype)

    if interval_summary:
        lines += ["", "## Intervals (auto-groups)", ""]
        for s in interval_summary:
            lines.append(f"- {s}")

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
        iso = activity_date.isocalendar()
        if iso[0] == year and iso[1] == week_num:
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
    sorted_acts = sorted(week_acts, key=lambda x: x.get("start_date_local", ""))
    last = sorted_acts[-1]
    ctl = last.get("icu_ctl")
    atl = last.get("icu_atl")
    tsb = round(ctl - atl, 1) if ctl and atl else None

    by_type = {}
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
    for t, stats in sorted(by_type.items()):
        lines.append(
            f"- {emoji(t)} **{t}** — {stats['count']}x, "
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


def sync(force: bool = False) -> None:
    state: State = load_state()

    last_sync: str | None = state.get("last_sync")
    if not force and last_sync:
        oldest: str = datetime.fromisoformat(last_sync).strftime("%Y-%m-%d")
    else:
        oldest: str = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

    newest: str = datetime.now().strftime("%Y-%m-%d")
    print(f"Fetching activities {oldest} → {newest}...")
    activities = cast(
        list[Activity], api_get(f"activities?oldest={oldest}&newest={newest}")
    )
    print(f"Found {len(activities)} activities")

    new_count = 0
    weeks_to_update = set()
    # Disk is the source of truth — read note ID from frontmatter (activity_id).
    id_to_path = scan_existing_notes()  # {act_id: relpath}
    claimed = {rp: aid for aid, rp in id_to_path.items()}  # {relpath: act_id}

    for a in activities:
        act_id = str(a.get("id", ""))
        if not act_id:
            continue
        if a.get("type") == "Walk":
            continue
        start = a.get("start_date_local", "")[:10]
        name = a.get("name", "Activity")
        # activities go into YYYY/MM subdirs (write_text_safe creates dirs)
        subdir = f"{start[:4]}/{start[5:7]}" if len(start) >= 7 else ""
        prefix = f"{subdir}/" if subdir else ""
        relpath = f"{prefix}{start} {safe_name(name)}.md"
        # Collision: a different activity (different ID) already claimed this name →
        # append ID to avoid overwriting (e.g. 2× "Gdansk Road Cycling" same day).
        owner = claimed.get(relpath)
        if owner is not None and owner != act_id:
            relpath = (
                f"{prefix}{start} {safe_name(name)}__{a.get('strava_id') or act_id}.md"
            )
        filepath = f"{ACTIVITIES_DIR}/{relpath}"

        # Note with this ID already exists at this path → skip (unless --force).
        if not force and id_to_path.get(act_id) == relpath and os.path.exists(filepath):
            claimed[relpath] = act_id
            continue

        # Disable elevation correction (DEM) — use device barometer, consistent
        # with Strava/Garmin. total_elevation_gain is recalculated server-side,
        # so we re-fetch the activity after the PUT.
        if a.get("use_elevation_correction"):
            if set_elevation_correction(act_id, False):
                time.sleep(2.5)
                fresh = get_activity(act_id)
                if fresh and fresh.get("total_elevation_gain") is not None:
                    a = fresh

        intervals_data = fetch_intervals(act_id)
        weather = None
        if a.get("start_date_local") and a.get("type") not in (
            "WeightTraining",
            "Workout",
            "VirtualRide",
            "Swim",
        ):
            weather = fetch_weather(DEFAULT_LAT, DEFAULT_LON, a["start_date_local"])
        note = activity_note(cast(Activity, a), intervals_data, weather)
        if not write_text_safe(filepath, note):
            continue

        # Rename: same ID was previously at a different path → delete old note.
        old_rel = id_to_path.get(act_id)
        if old_rel and old_rel != relpath:
            old_path = f"{ACTIVITIES_DIR}/{old_rel}"
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                    print(f"  🗑  removed old note: {old_rel}")
                except OSError:
                    pass
            claimed.pop(old_rel, None)
        id_to_path[act_id] = relpath
        claimed[relpath] = act_id

        new_count += 1
        dt = datetime.strptime(start, "%Y-%m-%d")
        iso = dt.isocalendar()
        weeks_to_update.add((iso[0], iso[1]))
        print(f"  ✓ {relpath}")

    for year, week_num in weeks_to_update:
        summary = week_summary(activities, year, week_num)
        if summary:
            wf = f"{WEEKLY_DIR}/{year}-W{week_num:02d}-sport.md"
            if write_text_safe(wf, summary):
                print(f"  📊 {year}-W{week_num:02d}-sport.md updated")

    save_state({"last_sync": datetime.now().isoformat()})
    print(
        f"\nDone: {new_count} activities updated, {len(weeks_to_update)} weeks regenerated"
    )


if __name__ == "__main__":
    try:
        sync("--force" in sys.argv)
    except urllib.error.URLError as e:
        # exit cleanly instead of dumping a traceback / exit 1
        print(f"No network / connection error — skipping this run: {e}")
        sys.exit(0)
