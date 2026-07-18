import glob
import os
import re
import sys
import time
import urllib.error
from datetime import datetime, timedelta
from typing import cast

from .api import api_get, fetch_intervals, get_activity, set_elevation_correction
from .config import (
    LOOKBACK_DAYS,
    WEATHER_EXCLUDED_TYPES,
    ConfigError,
    get_settings,
)
from .formatters import iso_year_week, sanitize_filename
from .notes import activity_note, week_summary
from .state import Activity, State, load_state, save_state
from .weather import fetch_weather


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
    last_error: OSError | None = None
    for attempt in range(retries):
        try:
            with open(tmp, "w") as f:
                f.write(content)
            os.replace(tmp, path)
            return True
        except OSError as e:
            last_error = e
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    print(f"  ⚠️  failed to save {os.path.basename(path)}: {last_error}")
    return False


def scan_existing_notes(activities_dir: str) -> dict[str, str]:
    """Map of {activity_id: relpath} read from frontmatter of existing notes.

    Disk is the source of truth for rename detection and collision avoidance —
    the ID lives in the note itself (activity_id:), so we don't rely on an
    external state file that may drift or be unaware of pre-tracking notes."""
    existing_notes: dict[str, str] = {}
    for note_path in glob.glob(f"{activities_dir}/**/*.md", recursive=True):
        try:
            with open(note_path) as f:
                head = f.read(800)
        except OSError:
            continue
        match = re.search(r"(?m)^activity_id:\s*(\S+)\s*$", head)
        if match:
            existing_notes[match.group(1)] = os.path.relpath(note_path, activities_dir)
    return existing_notes


def sync(force: bool = False) -> None:
    settings = get_settings()
    activities_dir = settings["activities_dir"]
    weekly_dir = settings["weekly_dir"]
    default_lat = settings["default_lat"]
    default_lon = settings["default_lon"]

    state: State = load_state()

    last_sync: str | None = state.get("last_sync")
    oldest: str
    if not force and last_sync:
        oldest = datetime.fromisoformat(last_sync).strftime("%Y-%m-%d")
    else:
        oldest = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    newest: str = datetime.now().strftime("%Y-%m-%d")
    print(f"Fetching activities {oldest} → {newest}...")
    activities = cast(
        list[Activity], api_get(f"activities?oldest={oldest}&newest={newest}")
    )
    print(f"Found {len(activities)} activities")

    new_count = 0
    weeks_to_update = set()
    # Disk is the source of truth — read note ID from frontmatter (activity_id).
    id_to_path = scan_existing_notes(activities_dir)  # {act_id: relpath}
    claimed = {rp: aid for aid, rp in id_to_path.items()}  # {relpath: act_id}

    for activity in activities:
        act_id = str(activity.get("id", ""))
        if not act_id:
            continue
        if activity.get("type") == "Walk":
            continue
        start = activity.get("start_date_local", "")[:10]
        name = activity.get("name", "Activity")
        # activities go into YYYY/MM subdirs (write_text_safe creates dirs)
        subdir = f"{start[:4]}/{start[5:7]}" if len(start) >= 7 else ""
        prefix = f"{subdir}/" if subdir else ""
        relpath = f"{prefix}{start} {sanitize_filename(name)}.md"
        # Collision: a different activity (different ID) already claimed this name →
        # append ID to avoid overwriting (e.g. 2× "Gdansk Road Cycling" same day).
        owner = claimed.get(relpath)
        if owner is not None and owner != act_id:
            relpath = f"{prefix}{start} {sanitize_filename(name)}__{activity.get('strava_id') or act_id}.md"
        filepath = f"{activities_dir}/{relpath}"

        # Note with this ID already exists at this path → skip (unless --force).
        if not force and id_to_path.get(act_id) == relpath and os.path.exists(filepath):
            claimed[relpath] = act_id
            continue

        # Disable elevation correction (DEM) — use device barometer, consistent
        # with Strava/Garmin. total_elevation_gain is recalculated server-side,
        # so we re-fetch the activity after the PUT.
        if activity.get("use_elevation_correction"):
            if set_elevation_correction(act_id, False):
                time.sleep(2.5)
                fresh = get_activity(act_id)
                if fresh and fresh.get("total_elevation_gain") is not None:
                    activity = fresh

        intervals_data = fetch_intervals(act_id)
        weather = None
        if (
            activity.get("start_date_local")
            and activity.get("type") not in WEATHER_EXCLUDED_TYPES
        ):
            weather = fetch_weather(
                default_lat, default_lon, activity["start_date_local"]
            )
        note = activity_note(activity, intervals_data, weather)
        if not write_text_safe(filepath, note):
            continue

        # Rename: same ID was previously at a different path → delete old note.
        old_rel = id_to_path.get(act_id)
        if old_rel and old_rel != relpath:
            old_path = f"{activities_dir}/{old_rel}"
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
        weeks_to_update.add(iso_year_week(start))
        print(f"  ✓ {relpath}")

    for year, week_num in weeks_to_update:
        summary = week_summary(
            [a for a in activities if a.get("type") != "Walk"], year, week_num
        )
        if summary:
            weekly_note_path = f"{weekly_dir}/{year}-W{week_num:02d}-sport.md"
            if write_text_safe(weekly_note_path, summary):
                print(f"  📊 {year}-W{week_num:02d}-sport.md updated")

    save_state({"last_sync": datetime.now().isoformat()})
    print(
        f"\nDone: {new_count} activities updated, {len(weeks_to_update)} weeks regenerated"
    )


def main() -> int:
    """Console-script entry point: parse argv, run sync, translate expected
    failures into friendly messages and exit codes instead of tracebacks."""
    try:
        sync("--force" in sys.argv)
    except ConfigError as error:
        # missing/malformed credentials — print the guidance, not a traceback
        print(f"Configuration error: {error}")
        return 1
    except urllib.error.URLError as error:
        # exit cleanly instead of dumping a traceback / exit 1
        print(f"No network / connection error — skipping this run: {error}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
