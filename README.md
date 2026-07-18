# intervals-sync

Syncs [intervals.icu](https://intervals.icu) activities to Obsidian markdown notes.

- Activity notes → `YYYY/MM/YYYY-MM-DD <name>.md` under `activities_dir`
- Weekly summaries → `YYYY-Www-sport.md` under `weekly_dir`
- No third-party dependencies — stdlib only

## Setup

### 1. Install

```bash
uv sync
```

### 2. Configure credentials

Copy `secrets.json.example` → `secrets.json` (gitignored) and fill in your values:

```json
{
  "athlete_id": "...",
  "api_key": "...",
  "activities_dir": "/path/to/vault/activities",
  "weekly_dir": "/path/to/vault/weekly"
}
```

`api_key` comes from intervals.icu → Settings → Developer.

Alternatively, set environment variables: `INTERVALS_ATHLETE_ID`, `INTERVALS_API_KEY`, `INTERVALS_ACTIVITIES_DIR`, `INTERVALS_WEEKLY_DIR`.

### 3. Run

```bash
uv run intervals-sync             # sync last 60 days, skip already-synced
uv run intervals-sync --force     # regenerate all notes in the window
```

### 4. Schedule (macOS)

A launchd plist at `~/Library/LaunchAgents/com.michaldomarus.intervals-sync.plist` runs the sync daily at 07:00.

## How it works

**Activity notes** are written to `YYYY/MM/YYYY-MM-DD <name>.md`. Each note has YAML frontmatter with `activity_id` — this is the source of truth for detecting renames and collisions. If an activity is renamed on intervals.icu, the old note is deleted and a new one is written. If two activities share the same name and date, the second gets a `__{strava_id}` suffix.

**Elevation** — `use_elevation_correction` (DEM) is disabled per activity so `total_elevation_gain` matches the device barometer, consistent with Strava/Garmin. The activity is re-fetched after the PUT to pick up the recalculated value.

**Weather** — temperature and wind at activity start time are fetched from Open-Meteo (up to 92 days back) and appended to the note.

**Splits** — structured WORK/RECOVERY interval data from intervals.icu is rendered as a markdown table.

**Atomic writes** — notes are written to a `.tmp` file and swapped via `os.replace()` to avoid iCloud File Provider locks.

## Project structure

```
src/intervals_sync/
  config.py   — credentials loading and module-level constants
  api.py      — HTTP primitive and all intervals.icu API calls
  notes.py    — formatting helpers, activity_note, week_summary
  sync.py     — orchestration: scan, write, rename, weekly update
  state.py    — State / Activity TypedDicts, load/save last_sync
  weather.py  — Open-Meteo fetch
```

## Development

```bash
uv run ty check      # type checking
uv run ruff check    # linting
uv run ruff format   # formatting
```

Pre-commit hooks run all three automatically on `git commit`.
