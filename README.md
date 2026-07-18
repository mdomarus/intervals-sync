# intervals-sync

Syncs [intervals.icu](https://intervals.icu) activities to Obsidian markdown notes.

- Activity notes → `YYYY/MM/YYYY-MM-DD <name>.md` under `activities_dir`
- Weekly summaries → `YYYY-Www-sport.md` under `weekly_dir`
- No third-party runtime dependencies — stdlib only
- Requires Python 3.10+

## Setup

### 1. Install

```bash
uv sync
```

### 2. Configure

Copy `secrets.json.example` → `secrets.json` (gitignored) and fill in your values. The file is read from the package directory or the repo root:

```json
{
  "athlete_id": "...",
  "api_key": "...",
  "activities_dir": "/path/to/vault/activities",
  "weekly_dir": "/path/to/vault/weekly",
  "default_lat": 54.5189,
  "default_lon": 18.5305
}
```

`api_key` comes from intervals.icu → Settings → Developer. `default_lat`/`default_lon` are the coordinates used for the weather lookup — optional, and default to Gdynia (54.5189, 18.5305) when omitted.

Alternatively, set environment variables: `INTERVALS_ATHLETE_ID`, `INTERVALS_API_KEY`, `INTERVALS_ACTIVITIES_DIR`, `INTERVALS_WEEKLY_DIR`, and optionally `INTERVALS_DEFAULT_LAT`, `INTERVALS_DEFAULT_LON`.

### 3. Run

```bash
uv run intervals-sync             # sync last 60 days, skip already-synced
uv run intervals-sync --force     # regenerate all notes in the window
```

### 4. Schedule (macOS)

```bash
./install.sh
```

Generates a launchd plist from the current environment (`$HOME`, `uv` path, repo location), installs it to `~/Library/LaunchAgents/`, and loads it. Runs daily at 07:00; logs go to `~/Library/Logs/intervals-sync.log`.

`install.sh` is macOS-only. On Linux, schedule `uv run intervals-sync` with cron or a systemd timer instead.

## How it works

**Activity notes** are written to `YYYY/MM/YYYY-MM-DD <name>.md`. Each note has YAML frontmatter with `activity_id` — this is the source of truth for detecting renames and collisions. If an activity is renamed on intervals.icu, the old note is deleted and a new one is written. If two activities share the same name and date, the second gets a `__{strava_id}` suffix.

**Elevation** — `use_elevation_correction` (DEM) is disabled per activity so `total_elevation_gain` matches the device barometer, consistent with Strava/Garmin. The activity is re-fetched after the PUT to pick up the recalculated value.

**Weather** — temperature and wind at activity start time are fetched from Open-Meteo (up to 92 days back) for the configured `default_lat`/`default_lon` and appended to the note. Skipped for indoor types (`WeightTraining`, `Workout`, `VirtualRide`, `Swim`).

**Splits** — structured WORK/RECOVERY interval data from intervals.icu is rendered as a markdown table.

**Atomic writes** — notes are written to a `.tmp` file and swapped via `os.replace()` to avoid iCloud File Provider locks.

## Project structure

```
src/intervals_sync/
  config.py   — settings loading (secrets.json / env) and module-level constants
  api.py      — HTTP primitive and all intervals.icu API calls
  notes.py    — formatting helpers, activity_note, week_summary
  sync.py     — orchestration: scan, write, rename, weekly update
  state.py    — State / Activity TypedDicts, load/save last_sync
  weather.py  — Open-Meteo fetch
```

## Development

```bash
uv run pytest        # tests
uv run ty check      # type checking
uv run ruff check    # linting
uv run ruff format   # formatting
```

Pre-commit hooks run format, lint, type check, and tests automatically on `git commit`. CI runs the same checks on Python 3.10 and 3.13 for every push and pull request.

## License

[MIT](LICENSE)
