import json
import os
from functools import lru_cache
from typing import TypedDict


class Settings(TypedDict):
    athlete_id: str
    api_key: str
    activities_dir: str
    weekly_dir: str
    default_lat: float
    default_lon: float


class ConfigError(RuntimeError):
    """Raised when required credentials or paths are missing or malformed.

    Carries a user-facing message so the CLI can print it instead of dumping a
    traceback when someone runs the tool before configuring it."""


# Gdynia — used for the weather lookup when the config doesn't override the location.
FALLBACK_LAT, FALLBACK_LON = 54.5189, 18.5305

INTERVALS_API_URL = "https://intervals.icu/api/v1"
# How far back to sync when there is no recorded last-sync timestamp.
LOOKBACK_DAYS = 60
# Socket timeout for all outbound HTTP requests (intervals.icu + Open-Meteo).
HTTP_TIMEOUT_SECONDS = 30
# Open-Meteo forecast API only serves up to this many past days.
WEATHER_MAX_PAST_DAYS = 92

# Distance/pace-based run types (get a Pace row and a run-shaped splits table).
RUN_TYPES = ("Run", "TrailRun")
# Indoor / GPS-less types that never get a weather lookup.
WEATHER_EXCLUDED_TYPES = ("WeightTraining", "Workout", "VirtualRide", "Swim")

# --- Weekly load-metric thresholds (deterministic interpretation labels) ---
# ACWR (acute:chronic workload ratio = ATL/CTL); Gabbett "sweet spot" bands.
ACWR_UNDERLOAD_MAX = 0.8
ACWR_OPTIMAL_MAX = 1.3
ACWR_ELEVATED_MAX = 1.5

# Ramp rate = week-over-week change in CTL (CTL points per week).
RAMP_SAFE_MAX = 5.0
RAMP_AGGRESSIVE_MAX = 8.0

# Week-over-week total-load change, in percent.
LOAD_WOW_JUMP_PCT = 30.0
LOAD_WOW_DELOAD_PCT = -30.0

# Foster training monotony = weekly mean load / population stdev of daily load.
MONOTONY_GOOD_MAX = 1.5
MONOTONY_MODERATE_MAX = 2.0

# How many trailing ISO weeks the weekly-summary trend table shows.
TREND_WEEKS = 6
# Days fetched before the sync window so the trend table has prior-week history:
# TREND_WEEKS weeks of rows, plus one extra week so the oldest row's ramp (ΔCTL
# vs the week before it) has a reference row to compare against.
WELLNESS_TREND_BUFFER_DAYS = TREND_WEEKS * 7 + 7

# Required settings and the environment variable each maps to (env fallback path).
_ENV_BY_KEY = {
    "athlete_id": "INTERVALS_ATHLETE_ID",
    "api_key": "INTERVALS_API_KEY",
    "activities_dir": "INTERVALS_ACTIVITIES_DIR",
    "weekly_dir": "INTERVALS_WEEKLY_DIR",
}


def _find_secrets_file() -> str | None:
    """Locate secrets.json, checking the package directory first and then the
    repo root (two levels up from src/intervals_sync/). Returns None if neither
    exists, in which case settings come from environment variables."""
    package_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(os.path.dirname(package_dir))
    for candidate in (
        os.path.join(package_dir, "secrets.json"),
        os.path.join(repo_root, "secrets.json"),
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def _load_from_secrets(secrets_path: str) -> Settings:
    try:
        with open(secrets_path) as secrets_file:
            secrets = json.load(secrets_file)
    except json.JSONDecodeError as error:
        raise ConfigError(f"Invalid JSON in {secrets_path}: {error}") from error
    missing_keys = [key for key in _ENV_BY_KEY if not secrets.get(key)]
    if missing_keys:
        raise ConfigError(
            f"{secrets_path} is missing required keys: {', '.join(missing_keys)}. "
            "See secrets.json.example for the expected shape."
        )
    return {
        "athlete_id": secrets["athlete_id"],
        "api_key": secrets["api_key"],
        "activities_dir": secrets["activities_dir"],
        "weekly_dir": secrets["weekly_dir"],
        "default_lat": float(secrets.get("default_lat", FALLBACK_LAT)),
        "default_lon": float(secrets.get("default_lon", FALLBACK_LON)),
    }


def _load_from_env() -> Settings:
    missing_vars = [env for env in _ENV_BY_KEY.values() if not os.environ.get(env)]
    if missing_vars:
        raise ConfigError(
            "No secrets.json found and required environment variables are not set: "
            f"{', '.join(missing_vars)}. Copy secrets.json.example to secrets.json "
            "or export the INTERVALS_* variables."
        )
    return {
        "athlete_id": os.environ["INTERVALS_ATHLETE_ID"],
        "api_key": os.environ["INTERVALS_API_KEY"],
        "activities_dir": os.environ["INTERVALS_ACTIVITIES_DIR"],
        "weekly_dir": os.environ["INTERVALS_WEEKLY_DIR"],
        "default_lat": float(os.environ.get("INTERVALS_DEFAULT_LAT", FALLBACK_LAT)),
        "default_lon": float(os.environ.get("INTERVALS_DEFAULT_LON", FALLBACK_LON)),
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings lazily from gitignored secrets.json (package dir or repo
    root), falling back to INTERVALS_* environment variables.

    Loading is deferred until first call (not import time) so the package can be
    imported and tested without credentials present. Raises ConfigError with a
    user-facing message when required values are absent or malformed. Coordinates
    are optional and fall back to Gdynia (FALLBACK_LAT / FALLBACK_LON)."""
    secrets_path = _find_secrets_file()
    if secrets_path is not None:
        return _load_from_secrets(secrets_path)
    return _load_from_env()
