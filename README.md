<div align="center">

# 🏃 intervals-sync

<strong>Your training log, in your vault.</strong><br/>
Sync <a href="https://intervals.icu">intervals.icu</a> activities to Obsidian markdown notes — stdlib only, no runtime dependencies.

<p>
  <a href="https://github.com/mdomarus/intervals-sync/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/mdomarus/intervals-sync/actions/workflows/ci.yml/badge.svg"/></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/License-MIT-22c55e?style=flat"/></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10+-3b82f6?style=flat&logo=python&logoColor=white"/>
  <img alt="Version" src="https://img.shields.io/badge/version-0.2.0-a855f7?style=flat"/>
  <img alt="Dependencies" src="https://img.shields.io/badge/runtime%20deps-0-f59e0b?style=flat"/>
</p>

<p>
  <a href="#-setup">Setup</a> •
  <a href="#-how-it-works">How it works</a> •
  <a href="#-weekly-load--trend-metrics">Load &amp; trend</a> •
  <a href="#-project-structure">Structure</a> •
  <a href="#-development">Development</a>
</p>

</div>

---

- 📝 Activity notes → `YYYY/MM/YYYY-MM-DD <name>.md` under `activities_dir`
- 📅 Weekly summaries → `YYYY-Www-sport.md` under `weekly_dir`, optionally including a deterministic **Load & trend** section (ACWR, ramp rate, week-over-week load, Foster monotony/strain, trailing trend table)
- 📦 No third-party runtime dependencies — stdlib only
- 🐍 Requires Python 3.10+

## ⚙️ Setup

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

```bash
./install.sh
```

Generates a launchd plist from the current environment (`$HOME`, `uv` path, repo location), installs it to `~/Library/LaunchAgents/`, and loads it. Runs daily at 07:00; logs go to `~/Library/Logs/intervals-sync.log`.

`install.sh` is macOS-only. On Linux, schedule `uv run intervals-sync` with cron or a systemd timer instead.

## 🔧 How it works

**Activity notes** are written to `YYYY/MM/YYYY-MM-DD <name>.md`. Each note has YAML frontmatter with `activity_id` — this is the source of truth for detecting renames and collisions. If an activity is renamed on intervals.icu, the old note is deleted and a new one is written. If two activities share the same name and date, the second gets a `__{strava_id}` suffix.

**Elevation** — `use_elevation_correction` (DEM) is disabled per activity so `total_elevation_gain` matches the device barometer, consistent with Strava/Garmin. The activity is re-fetched after the PUT to pick up the recalculated value.

**Weather** — temperature and wind at activity start time are fetched from Open-Meteo (up to 92 days back) at the activity's actual location and appended to the note. The location is the GPS point nearest the activity's time middle (from the `latlng` stream), so long point-to-point rides get weather for where they were, not a fixed home city. Skipped for indoor types (`WeightTraining`, `Workout`, `VirtualRide`, `Swim`) and for activities with no GPS fix — no weather is shown rather than a wrong reading.

**Splits** — structured WORK/RECOVERY interval data from intervals.icu is rendered as a markdown table.

**Zone tables** — time-in-zone is rendered as markdown tables. The `## Heart Rate` section gets an HR-zone table whose "Up to" column is each zone's upper bpm bound (intervals.icu stores `icu_hr_zones` as the upper limit of each zone; the last entry is HRmax). For runs, a `## Pace Zones` table shows pace and (when available) GAP side by side; its "Up to" column is each zone's upper pace bound, derived from your threshold pace (intervals.icu stores pace-zone boundaries as percentages of threshold, not absolute speeds), and the open-ended top zone has no bound.

**Cadence** — intervals.icu reports single-leg cadence. For runs it is doubled to total steps per minute (`spm`), matching the Garmin/Strava convention; cycling cadence is left as crank RPM.

**Units** — distance, pace, speed, elevation, temperature, and wind speed all follow your intervals.icu profile (`measurement_preference`, per-sport pace units, the `fahrenheit` flag, and the `wind_speed` setting), so notes render in km/mi, min/km or min/mi, km/h or mph, m/ft, °C or °F, and km/h · mph · m/s · kn · Bft to match your account.

**Atomic writes** — notes are written to a `.tmp` file and swapped via `os.replace()` to avoid iCloud File Provider locks.

## 📊 Weekly load & trend metrics

When wellness data provides usable values, the weekly summary includes a `## Load & trend` section computed deterministically from intervals.icu wellness data — no AI or LLM involved, purely arithmetic.

**Metrics explained:**

- **ACWR** (Acute:Chronic Workload Ratio) — ATL divided by CTL, the exponentially-weighted variant of the ratio. A value of 0.8–1.3 is the "sweet spot": enough stimulus to adapt without a large injury-risk spike. Above 1.5 is high risk; below 0.8 is underloading.
- **Ramp rate** (ΔCTL/week) — the week-over-week change in CTL (chronic training load, the Banister fitness score). A rise of up to ~5 pts/week is considered safe; 5–8 is aggressive but manageable; above 8 carries elevated injury risk. This is a coaching heuristic, not a hard clinical limit.
- **Week-over-week load %** — how much total weekly load changed relative to the prior week. Rises above +30% or drops below −30% are flagged as large swings — another coaching heuristic to avoid sudden spikes.
- **Monotony / Strain** — Foster training monotony is the weekly mean daily load divided by the standard deviation of daily load across the week. Low values mean varied training stimulus; above ~2.0 is considered elevated risk. Strain is weekly total load × monotony.
- **Trend table** — a six-week trailing table showing Week, CTL, weekly Load, and Ramp (ΔCTL), so you can see how load and fitness have evolved week by week. The current in-progress week is flagged with `*`.

**Sources:**

- Gabbett TJ. "The training—injury prevention paradox: should athletes be training smarter and harder?" *Br J Sports Med* 2016;50(5):273–280. doi:[10.1136/bjsports-2015-095788](https://doi.org/10.1136/bjsports-2015-095788) — ACWR sweet-spot and risk bands.
- Foster C. "Monitoring training in athletes with reference to overtraining syndrome." *Med Sci Sports Exerc* 1998;30(7):1164–1168. — Training monotony and strain.
- Ramp-rate (5–8 pts/week) and week-over-week load (±30%) bands are **coaching heuristics** from TrainingPeaks / Coggan & Allen's Performance Manager Chart and intervals.icu Fitness/Form documentation (https://intervals.icu), not single controlled studies.

## 🗂️ Project structure

```
src/intervals_sync/
  config.py   — settings loading (secrets.json / env) and module-level constants
  api.py      — HTTP primitive and all intervals.icu API calls
  notes.py    — formatting helpers, activity_note, week_summary
  sync.py     — orchestration: scan, write, rename, weekly update
  state.py    — State / Activity TypedDicts, load/save last_sync
  weather.py  — Open-Meteo fetch
```

## 🛠️ Development

```bash
uv run pytest        # tests
uv run ty check      # type checking
uv run ruff check    # linting
uv run ruff format   # formatting
```

Pre-commit hooks run format, lint, type check, and tests automatically on `git commit`. CI runs the same checks on Python 3.10 and 3.14 for every push and pull request.

## 📄 License

[MIT](LICENSE)
