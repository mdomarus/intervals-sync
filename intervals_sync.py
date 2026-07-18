#!/usr/bin/env python3

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
import base64
import math
import glob
import re
from datetime import datetime, timedelta, date


def _load_secrets():
    """athlete_id + api_key z gitignorowanego secrets.json obok skryptu
    (fallback: zmienne środowiskowe INTERVALS_ATHLETE_ID / INTERVALS_API_KEY, INTERVALS_VAULT_PATH)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets.json")
    if os.path.exists(path):
        with open(path) as f:
            s = json.load(f)
        return (
            s["athlete_id"],
            s["api_key"],
            s["activities_dir"],
            s["weekly_dir"],
        )
    return (
        os.environ["INTERVALS_ATHLETE_ID"],
        os.environ["INTERVALS_API_KEY"],
        os.environ["INTERVALS_ACTIVITIES_DIR"],
        os.environ["INTERVALS_WEEKLY_DIR"],
    )


INTERVALS_API_URL = "https://intervals.icu/api/v1"
ATHLETE_ID, API_KEY, ACTIVITIES_DIR, WEEKLY_DIR = _load_secrets()
STATE_FILE = os.path.expanduser("~/.intervals_sync_state.json")
DEFAULT_LAT, DEFAULT_LON = (
    54.5189,
    18.5305,
)  # Gdynia — fallback gdy aktywność nie ma GPS


def write_text_safe(path, content, retries=4, delay=1.5):
    """Atomowy, odporny na iCloud zapis pliku.

    Pisze do pliku tymczasowego w tym samym katalogu i podmienia przez
    os.replace() (atomowy rename). Rename obchodzi lock File Providera iCloud,
    który zwykły open(path, "w") dostaje jako `Operation not permitted` (EPERM),
    gdy plik jest w trakcie synchronizacji — to była przyczyna padów o 07:00.
    Ponawia przy przejściowym OSError. Zwraca True/False (False = nie uda się
    zapisać; wołający decyduje czy kontynuować, zamiast wysypywać cały przebieg).
    """
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f".{os.path.basename(path)}.tmp.{os.getpid()}")
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
    print(f"  ⚠️  nie udało się zapisać {os.path.basename(path)}: {last}")
    return False


def api_get(path: str):
    url = f"{INTERVALS_API_URL}/athlete/{ATHLETE_ID}/{path}"
    creds = base64.b64encode(f"API_KEY:{API_KEY}".encode()).decode()
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {creds}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 intervals-sync",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def get_activity(act_id: str):
    """Świeży pojedynczy rekord aktywności (np. po zmianie ustawień serwerowych)."""
    try:
        url = f"{INTERVALS_API_URL}/activity/{act_id}"
        creds = base64.b64encode(f"API_KEY:{API_KEY}".encode()).decode()
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Basic {creds}",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 intervals-sync",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  ⚠ activity refetch failed for {act_id}: {e}")
        return None


def set_elevation_correction(act_id: str, value: bool):
    """Wyłącza/włącza korektę elewacji intervals.icu (DEM). Wyłączona = zegarek
    (barometr) — wartość zgodna ze Stravą/Garminem, której ufa Michał. Zwraca
    True przy sukcesie. Po PUT serwer przelicza total_elevation_gain asynchronicznie."""
    try:
        url = f"{INTERVALS_API_URL}/activity/{act_id}"
        creds = base64.b64encode(f"API_KEY:{API_KEY}".encode()).decode()
        data = json.dumps({"use_elevation_correction": value}).encode()
        req = urllib.request.Request(
            url,
            data=data,
            method="PUT",
            headers={
                "Authorization": f"Basic {creds}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 intervals-sync",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"  ⚠ nie udało się ustawić elevation_correction dla {act_id}: {e}")
        return False


def hms(s):
    if not s:
        return "—"
    s = int(s)
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h}:{m:02d}:{sec:02d}"


def pace(dist_m, time_s):
    if not dist_m or not time_s:
        return None
    ps = time_s / (dist_m / 1000)
    m, s = divmod(int(ps), 60)
    return f"{m}:{s:02d} /km"


def speed_kmh(mps):
    if not mps:
        return None
    return round(mps * 3.6, 1)


def emoji(t):
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


def safe_name(s):
    import unicodedata

    def keep(c):
        if c.isalnum() or c in " -_":
            return True
        cat = unicodedata.category(c)
        return cat in ("So", "Sm", "Sk", "Sc")  # emoji i symbole Unicode

    return "".join(c if keep(c) else "_" for c in s)


def scan_existing_notes():
    """Mapa {activity_id: relpath} z frontmattera istniejących notatek.

    Dysk jest źródłem prawdy dla wykrywania zmiany nazwy i kolizji — ID siedzi
    w samej notatce (`activity_id:`), więc nie polegamy na zewnętrznym pliku
    stanu (który może się rozjechać albo nie znać notatek sprzed śledzenia)."""
    out = {}
    for p in glob.glob(f"{ACTIVITIES_DIR}/**/*.md", recursive=True):
        try:
            with open(p) as f:
                head = f.read(800)
        except OSError:
            continue
        m = re.search(r"(?m)^activity_id:\s*(\S+)\s*$", head)
        if m:
            out[m.group(1)] = os.path.relpath(p, ACTIVITIES_DIR)
    return out


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"synced_ids": [], "paths": {}, "last_sync": None}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def val(a, key, default=None):
    v = a.get(key)
    return default if v is None else v


def row(label, value, unit=""):
    if value is None or value == "" or value == "—":
        return None
    return f"- **{label}:** {value}{(' ' + unit) if unit else ''}  "


def hr_zones_summary(zone_times, zone_limits):
    if not zone_times or not zone_limits:
        return None
    total = sum(zone_times)
    if total == 0:
        return None
    labels = ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]
    parts = []
    for i, (t, lim) in enumerate(zip(zone_times, zone_limits)):
        if t > 0:
            pct = round(t / total * 100)
            mins = t // 60
            parts.append(f"{labels[i]} ({lim}+bpm): {mins}min ({pct}%)")
    return " | ".join(parts)


def fetch_streams(act_id: str):
    """Pobiera streams (time, latlng) — używane do obliczenia bearing per split."""
    try:
        url = f"{INTERVALS_API_URL}/activity/{act_id}/streams"
        creds = base64.b64encode(f"API_KEY:{API_KEY}".encode()).decode()
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Basic {creds}",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 intervals-sync",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return {s.get("type"): s.get("data") for s in data}
    except Exception as e:
        print(f"  ⚠ streams fetch failed for {act_id}: {e}")
        return {}


def fetch_weather(lat, lon, start_iso):
    """Open-Meteo forecast API z past_days — działa dla dzisiaj i do 92 dni wstecz."""
    try:
        start_dt = (
            datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            if "T" in start_iso
            else datetime.strptime(start_iso[:10], "%Y-%m-%d")
        )
        days_back = max(1, (datetime.now() - start_dt).days + 1)
        if days_back > 92:
            return None
        params = urllib.parse.urlencode(
            {
                "latitude": f"{lat:.4f}",
                "longitude": f"{lon:.4f}",
                "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m,temperature_2m",
                "wind_speed_unit": "kmh",
                "timezone": "auto",
                "past_days": days_back,
                "forecast_days": 1,
            }
        )
        url = f"https://api.open-meteo.com/v1/forecast?{params}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        target = start_dt.strftime("%Y-%m-%dT%H:00")
        idx = next((i for i, t in enumerate(times) if t == target), None)
        if idx is None:
            return None
        return {
            "wind_speed": hourly["wind_speed_10m"][idx],
            "wind_dir": hourly["wind_direction_10m"][idx],
            "wind_gust": hourly["wind_gusts_10m"][idx],
            "temp": hourly["temperature_2m"][idx],
        }
    except Exception as e:
        print(f"  ⚠ weather fetch failed: {e}")
        return None


def bearing(lat1, lon1, lat2, lon2):
    """Bearing (kierunek ruchu) w stopniach, 0=N, 90=E."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def wind_label(course_deg, wind_from_deg):
    """Względny kąt wiatr→kierunek biegu. Wind 'from' = skąd wieje."""
    if course_deg is None or wind_from_deg is None:
        return "—"
    rel = ((course_deg - wind_from_deg + 540) % 360) - 180
    a = abs(rel)
    if a < 30:
        return f"⬆️ head ({a:.0f}°)"
    if a > 150:
        return f"⬇️ tail ({180 - a:.0f}°)"
    side = "↗" if rel > 0 else "↖"
    if a < 60:
        return f"{side} head-cross"
    if a > 120:
        return f"{side} tail-cross"
    return f"{side} cross"


def fetch_intervals(act_id):
    """Pobiera szczegółowe splity (WORK/RECOVERY) dla aktywności."""
    try:
        url = f"{INTERVALS_API_URL}/activity/{act_id}/intervals"
        creds = base64.b64encode(f"API_KEY:{API_KEY}".encode()).decode()
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Basic {creds}",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 intervals-sync",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  ⚠ intervals fetch failed for {act_id}: {e}")
        return None


def split_bearing(latlng, time_stream, start_index, moving_time):
    """Bearing splitu na podstawie latlng od start_index do start_index+moving_time."""
    if not latlng or not time_stream:
        return None
    n = len(latlng)
    if start_index >= n:
        return None
    end = min(start_index + moving_time, n - 1)
    if end <= start_index:
        return None
    lat1, lon1 = latlng[start_index]
    lat2, lon2 = latlng[end]
    if lat1 == lat2 and lon1 == lon2:
        return None
    return bearing(lat1, lon1, lat2, lon2)


def splits_table(intervals_data, atype, streams=None, weather=None):
    """Buduje tabelę splitów z odpowiedzi /intervals + wiatr per split."""
    if not intervals_data:
        return []
    ivs = intervals_data.get("icu_intervals") or []
    if not ivs:
        return []
    is_run = atype in ("Run", "TrailRun")
    latlng = (streams or {}).get("latlng")
    time_stream = (streams or {}).get("time")
    wind_dir = (weather or {}).get("wind_dir")
    show_wind = bool(latlng and wind_dir is not None)
    lines = ["", "## Splity (intervals.icu)", ""]
    if is_run:
        hdr = (
            "| # | Typ | Dystans | Czas | Tempo | GAP | HR avg | HR max | Zone | Int |"
        )
        sep = "|--:|:---|--------:|-----:|------:|----:|-------:|-------:|-----:|----:|"
    else:
        hdr = "| # | Typ | Dystans | Czas | Speed | HR avg | HR max | Zone | Int |"
        sep = "|--:|:---|--------:|-----:|------:|-------:|-------:|-----:|----:|"
    if show_wind:
        hdr += " Wiatr |"
        sep += "------|"
    lines.append(hdr)
    lines.append(sep)
    for i, iv in enumerate(ivs, 1):
        t = iv.get("type", "")
        t_short = "🟢 WORK" if t == "WORK" else ("⚪ REC" if t == "RECOVERY" else t)
        dist = iv.get("distance", 0) or 0
        mt = iv.get("moving_time", 0) or 0
        hr = int(iv["average_heartrate"]) if iv.get("average_heartrate") else "—"
        hrx = int(iv["max_heartrate"]) if iv.get("max_heartrate") else "—"
        z = iv.get("zone") or "—"
        intens = f"{int(iv['intensity'])}%" if iv.get("intensity") else "—"
        dist_s = f"{dist / 1000:.2f} km" if dist else "—"
        time_s = hms(mt) if mt else "—"
        if is_run:
            p = pace(dist, mt) or "—"
            gap_mps = iv.get("gap")
            gap_s = pace(1000, 1000 / gap_mps) if gap_mps else "—"
            row = f"| {i} | {t_short} | {dist_s} | {time_s} | {p} | {gap_s} | {hr} | {hrx} | Z{z} | {intens} |"
        else:
            sp = speed_kmh(iv.get("average_speed"))
            sp_s = f"{sp} km/h" if sp else "—"
            row = f"| {i} | {t_short} | {dist_s} | {time_s} | {sp_s} | {hr} | {hrx} | Z{z} | {intens} |"
        if show_wind:
            crs = split_bearing(latlng, time_stream, iv.get("start_index", 0), mt)
            row += f" {wind_label(crs, wind_dir)} |"
        lines.append(row)
    return lines


def activity_note(a, intervals_data=None, streams=None, weather=None):
    atype = val(a, "type", "Unknown")
    act_id = val(a, "id", "")
    em = emoji(atype)
    name = val(a, "name", "Aktywność")
    start_raw = val(a, "start_date_local", "")
    start = start_raw[:16].replace("T", " ")
    date_str = start_raw[:10]

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
        f"# {em} {name}",
        "",
    ]
    if race:
        lines.append("> 🏁 **WYŚCIG**\n")

    # Podstawowe
    lines += ["## Podstawowe", ""]
    for r in filter(
        None,
        [
            row("Typ", atype),
            row("Data", start),
            row("Dystans", f"{dist_km}" if dist_km > 0 else None, "km"),
            row("Czas (moving)", hms(moving) if moving else None),
            row(
                "Czas (elapsed)",
                hms(elapsed) if elapsed and elapsed != moving else None,
            ),
            row("Tempo", pace_str),
            row("Prędkość avg", speed_str, "km/h"),
            row("Prędkość max", max_speed_str, "km/h"),
            row("Przewyższenie ↑", elev_gain if elev_gain > 0 else None, "m D+"),
            row("Przewyższenie ↓", elev_loss if elev_loss > 0 else None, "m D-"),
            row("Warmup", hms(warmup) if warmup else None),
            row("Cooldown", hms(cooldown) if cooldown else None),
        ],
    ):
        lines.append(r)

    # Tętno
    if hr_avg or hr_max:
        lines += ["", "## Tętno", ""]
        for r in filter(
            None,
            [
                row("HR avg", int(hr_avg) if hr_avg else None, "bpm"),
                row("HR max", int(hr_max) if hr_max else None, "bpm"),
                row("HR spoczynkowy", hr_rest, "bpm"),
                row("HR max (atlet)", hr_max_athlete, "bpm"),
                row("LTHR", lthr, "bpm"),
            ],
        ):
            lines.append(r)
        if zones_str:
            lines.append(f"- **Strefy HR:** {zones_str}  ")

    # Moc (jeśli dostępna)
    if power_avg or power_weighted:
        lines += ["", "## Moc", ""]
        for r in filter(
            None,
            [
                row("Moc avg", int(power_avg) if power_avg else None, "W"),
                row(
                    "Moc ważona (NP)",
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

    # Obciążenie treningowe
    lines += ["", "## Obciążenie treningowe", ""]
    for r in filter(
        None,
        [
            row("Training Load", round(training_load, 1) if training_load else None),
            row("TRIMP", round(trimp, 1) if trimp else None),
            row("HR Load", round(hr_load, 1) if hr_load else None),
            row("Suffer Score", int(suffer) if suffer else None),
            row("Intensywność sesji", f"{round(intensity, 1)}%" if intensity else None),
            row("Efficiency Factor", round(ef, 2) if ef else None),
            row("Decoupling", f"{round(decoupling, 1)}%" if decoupling else None),
            row("Polarization Index", round(polarization, 2) if polarization else None),
            row("CTL (forma)", round(ctl, 1) if ctl else None),
            row("ATL (zmęczenie)", round(atl, 1) if atl else None),
            row("TSB (świeżość)", round(ctl - atl, 1) if ctl and atl else None),
        ],
    ):
        lines.append(r)

    # Odczucia
    if rpe or feel:
        lines += ["", "## Odczucia", ""]
        for r in filter(
            None,
            [
                row("RPE", rpe),
                row("Feel", feel),
            ],
        ):
            lines.append(r)

    # Warunki
    if temp_avg is not None:
        lines += ["", "## Warunki", ""]
        for r in filter(
            None,
            [
                row("Temperatura avg", f"{round(temp_avg, 1)}", "°C"),
                row(
                    "Temperatura min/max",
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

    # Inne
    lines += ["", "## Inne", ""]
    for r in filter(
        None,
        [
            row("Kadencja", int(cadence) if cadence else None),
            row("Kalorie", int(calories) if calories else None, "kcal"),
            row("Waga", weight, "kg"),
            row("Urządzenie", device),
            row("Źródło", source),
        ],
    ):
        lines.append(r)
    if strava_id:
        lines.append(
            f"- **Strava:** [link](https://www.strava.com/activities/{strava_id})  "
        )

    # Pogoda (z Open-Meteo, jeśli intervals.icu nie ma własnej)
    if weather:
        lines += ["", "## Pogoda (Open-Meteo)", ""]
        for r in filter(
            None,
            [
                row(
                    "Temperatura",
                    f"{round(weather['temp'], 1)}"
                    if weather.get("temp") is not None
                    else None,
                    "°C",
                ),
                row(
                    "Wiatr",
                    f"{round(weather['wind_speed'], 1)} km/h od {int(weather['wind_dir'])}°"
                    if weather.get("wind_speed") is not None
                    else None,
                ),
                row(
                    "Porywy",
                    f"{round(weather['wind_gust'], 1)}"
                    if weather.get("wind_gust") is not None
                    else None,
                    "km/h",
                ),
            ],
        ):
            lines.append(r)

    # Splity szczegółowe (WORK/RECOVERY z /intervals endpoint, z wiatrem per split)
    lines += splits_table(intervals_data, atype, streams, weather)

    # Interwały (auto-grupy z interval_summary)
    if interval_summary:
        lines += ["", "## Interwały (auto-grupy)", ""]
        for s in interval_summary:
            lines.append(f"- {s}")

    # Opis
    if description:
        lines += ["", "## Opis", "", description]

    return "\n".join(lines)


def week_summary(activities, year, week_num):
    week_acts = []
    for a in activities:
        d = a.get("start_date_local", "")[:10]
        if not d:
            continue
        dt = datetime.strptime(d, "%Y-%m-%d")
        iso = dt.isocalendar()
        if iso[0] == year and iso[1] == week_num:
            week_acts.append(a)
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

    # CTL/ATL z ostatniej aktywności tygodnia
    sorted_acts = sorted(week_acts, key=lambda x: x.get("start_date_local", ""))
    last = sorted_acts[-1]
    ctl = last.get("icu_ctl")
    atl = last.get("icu_atl")
    tsb = round(ctl - atl, 1) if ctl and atl else None

    by_type = {}
    for a in week_acts:
        t = a.get("type", "Unknown")
        by_type.setdefault(t, {"count": 0, "dist": 0, "time": 0, "elev": 0})
        by_type[t]["count"] += 1
        by_type[t]["dist"] += (a.get("distance", 0) or 0) / 1000
        by_type[t]["time"] += a.get("moving_time", 0) or 0
        by_type[t]["elev"] += int(a.get("total_elevation_gain", 0) or 0)

    lines = [
        "---",
        "type: note",
        "status: active",
        "tags: [sport, weekly-summary]",
        "area: life",
        f"week: {year}-W{week_num:02d}",
        "---",
        "",
        f"# 📊 Tygodniowe podsumowanie sportu — {year}-W{week_num:02d}",
        f"**Okres:** {week_start.strftime('%d.%m')} – {week_end.strftime('%d.%m.%Y')}",
        "",
        "## Łącznie",
        "",
        f"- **Aktywności:** {len(week_acts)}",
        f"- **Dystans:** {round(total_dist, 1)} km",
        f"- **Czas:** {hms(total_time)}",
        f"- **Przewyższenie:** {total_elev} m D+",
    ]
    if total_load:
        lines.append(f"- **Training Load:** {round(total_load, 1)}")
    if total_trimp:
        lines.append(f"- **TRIMP:** {round(total_trimp, 1)}")
    if total_cal:
        lines.append(f"- **Kalorie:** {int(total_cal)} kcal")
    if ctl:
        lines.append(f"- **CTL (forma):** {round(ctl, 1)}")
    if atl:
        lines.append(f"- **ATL (zmęczenie):** {round(atl, 1)}")
    if tsb is not None:
        tsb_label = (
            "świeży 💪" if tsb > 5 else ("zmęczony 😴" if tsb < -10 else "neutralny")
        )
        lines.append(f"- **TSB (świeżość):** {tsb} ({tsb_label})")

    lines += ["", "## Według typu", ""]
    for t, stats in sorted(by_type.items()):
        lines.append(
            f"- {emoji(t)} **{t}** — {stats['count']}x, "
            f"{round(stats['dist'], 1)} km, {hms(stats['time'])}, {stats['elev']} m D+"
        )

    lines += ["", "## Aktywności", ""]
    for a in sorted_acts:
        em = emoji(a.get("type", ""))
        name = a.get("name", "Aktywność")
        d = a.get("start_date_local", "")[:10]
        dist = round((a.get("distance", 0) or 0) / 1000, 1)
        load = a.get("icu_training_load")
        load_str = f" | Load: {round(load, 1)}" if load else ""
        sn = safe_name(name)
        lines.append(f"- {em} [[{d} {sn}]] — {dist} km{load_str}")

    return "\n".join(lines)


def sync(force=False):
    oldest = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    newest = datetime.now().strftime("%Y-%m-%d")
    print(f"Pobieram aktywności {oldest} → {newest}...")
    activities = api_get(f"activities?oldest={oldest}&newest={newest}")
    print(f"Znaleziono {len(activities)} aktywności")

    new_count = 0
    weeks_to_update = set()
    # Dysk = źródło prawdy. ID notatki czytamy z frontmattera (activity_id).
    id_to_path = scan_existing_notes()  # {act_id: relpath}
    claimed = {rp: aid for aid, rp in id_to_path.items()}  # {relpath: act_id}

    for a in activities:
        act_id = str(a.get("id", ""))
        if not act_id:
            continue
        if a.get("type") == "Walk":
            continue
        start = a.get("start_date_local", "")[:10]
        name = a.get("name", "Aktywnosc")
        # treningi w podfolderach YYYY/MM (write_text_safe tworzy katalogi)
        subdir = f"{start[:4]}/{start[5:7]}" if len(start) >= 7 else ""
        prefix = f"{subdir}/" if subdir else ""
        relpath = f"{prefix}{start} {safe_name(name)}.md"
        # Kolizja: inna aktywność (inne ID) zajęła już tę nazwę → dopisz ID,
        # żeby jej nie nadpisać (np. 2× „Gdansk Road Cycling" tego samego dnia).
        owner = claimed.get(relpath)
        if owner is not None and owner != act_id:
            relpath = (
                f"{prefix}{start} {safe_name(name)}__{a.get('strava_id') or act_id}.md"
            )
        filepath = f"{ACTIVITIES_DIR}/{relpath}"

        # Notatka z tym ID już jest pod tą samą ścieżką → pomiń (chyba że --force).
        if not force and id_to_path.get(act_id) == relpath and os.path.exists(filepath):
            claimed[relpath] = act_id
            continue

        # Wyłącz korektę elewacji (DEM) — chcemy wartość z zegarka (barometr),
        # zgodną ze Stravą/Garminem. total_elevation_gain jest przeliczane po
        # stronie serwera, więc po PUT odświeżamy rekord aktywności.
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
        note = activity_note(a, intervals_data, None, weather)
        if not write_text_safe(filepath, note):
            continue

        # Zmiana nazwy: notatka tego samego ID była pod inną ścieżką → usuń starą.
        old_rel = id_to_path.get(act_id)
        if old_rel and old_rel != relpath:
            old_path = f"{ACTIVITIES_DIR}/{old_rel}"
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                    print(f"  🗑  usunięto starą nazwę: {old_rel}")
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
                print(f"  📊 {year}-W{week_num:02d}-sport.md zaktualizowany")

    save_state({"last_sync": datetime.now().isoformat()})
    print(
        f"\nGotowe: {new_count} zaktualizowanych aktywności, {len(weeks_to_update)} tygodni"
    )


if __name__ == "__main__":
    try:
        sync("--force" in sys.argv)
    except urllib.error.URLError as e:
        # Brak sieci o 07:00 — wyjdź czysto zamiast wysypywać traceback / exit 1
        print(f"Brak sieci / błąd połączenia — pomijam ten przebieg: {e}")
        sys.exit(0)
