# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                        # install deps / create venv
uv run intervals-sync          # sync last 60 days, skip already-synced
uv run intervals-sync --force  # force regenerate all notes in the 60-day window
uv run pytest                  # run the test suite
uv run ty check                # type checking (ty, not mypy)
uv run ruff check              # linting
uv run ruff format             # formatting
pre-commit install             # install git hooks
```

Tests live in `tests/` and cover the pure formatters and config loading. Run them with `uv run pytest`.

## Architecture

A stdlib-only CLI (`intervals-sync` entry point → `sync.sync`) that syncs [intervals.icu](https://intervals.icu) activities to Obsidian markdown notes. No third-party runtime dependencies.

```
src/intervals_sync/
  config.py     — settings loading via get_settings() (lazy, cached) and module constants
  api.py        — single HTTP primitive _request(), intervals.icu API calls
  formatters.py — pure formatting helpers (duration, pace, splits table, …)
  notes.py      — activity_note(), week_summary()
  sync.py       — orchestration: scan existing notes, write, rename, update weekly summaries; main() entry point
  state.py      — Activity/State TypedDicts, ~/.intervals_sync_state.json persistence
  weather.py    — Open-Meteo fetch (no API key)
```

### Key data flow

`sync()` in `sync.py`:
1. Loads state (last sync timestamp) from `~/.intervals_sync_state.json`.
2. Fetches activity list from intervals.icu API.
3. For each activity: disables DEM elevation correction (PUT) and re-fetches; fetches intervals and weather; renders markdown via `notes.activity_note()`; writes atomically to `YYYY/MM/YYYY-MM-DD <name>.md`.
4. Regenerates weekly summaries (`YYYY-Www-sport.md`) for all affected weeks.
5. Saves updated state.

### Important design decisions

- **Disk is source of truth**: `scan_existing_notes()` reads `activity_id:` from YAML frontmatter of every existing note to detect renames and collisions — no separate index.
- **Atomic writes**: `write_text_safe()` writes to `.{name}.tmp.{pid}` then `os.replace()` to avoid iCloud File Provider EPERM.
- **Elevation**: DEM correction is explicitly disabled per activity so `total_elevation_gain` matches the device barometer (consistent with Strava/Garmin).
- **Weather**: skipped for indoor types (`WeightTraining`, `Workout`, `VirtualRide`, `Swim`) and activities older than 92 days.
- **Type checker**: `ty` (Astral), not mypy. Ignore `.mypy_cache` if present.

## Code style

- **Meaningful names**: every variable, parameter, and function must be named for what it represents — no `data`, `res`, `tmp`, `val`, `item`, `x`.
- **Short files**: keep modules focused; if a file grows beyond ~150 lines, look for a natural split.
- **Small functions**: a function should do one thing. Extract when logic becomes non-trivial or reuse appears.
- **No silent failures**: raise or propagate specific exceptions with context; never bare `except` or swallowed errors.
- **No magic literals**: name constants at module level in `config.py` rather than scattering raw numbers or strings.
- **Typing**: annotate all functions (parameters and return types). Model structured data as `TypedDict` rather than plain `dict`. Use `type` aliases for complex annotations. Run `uv run ty check` and keep it clean.

### Credentials

Loaded from `secrets.json` (adjacent to the installed package, gitignored) or env vars: `INTERVALS_ATHLETE_ID`, `INTERVALS_API_KEY`, `INTERVALS_ACTIVITIES_DIR`, `INTERVALS_WEEKLY_DIR`. See `secrets.json.example` for the JSON shape.
