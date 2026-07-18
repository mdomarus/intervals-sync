import json
import os
from typing import TypedDict


class Settings(TypedDict):
    athlete_id: str
    api_key: str
    activities_dir: str
    weekly_dir: str
    default_lat: float
    default_lon: float


# Gdynia — used for the weather lookup when secrets don't override the location.
FALLBACK_LAT, FALLBACK_LON = 54.5189, 18.5305


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


def _load_settings() -> Settings:
    """Load settings from gitignored secrets.json (package dir or repo root),
    falling back to env vars INTERVALS_ATHLETE_ID / INTERVALS_API_KEY / ….

    Coordinates (default_lat / default_lon) are optional in both sources and
    fall back to Gdynia (FALLBACK_LAT / FALLBACK_LON) when absent."""
    secrets_path = _find_secrets_file()
    if secrets_path is not None:
        with open(secrets_path) as secrets_file:
            secrets = json.load(secrets_file)
        return {
            "athlete_id": secrets["athlete_id"],
            "api_key": secrets["api_key"],
            "activities_dir": secrets["activities_dir"],
            "weekly_dir": secrets["weekly_dir"],
            "default_lat": float(secrets.get("default_lat", FALLBACK_LAT)),
            "default_lon": float(secrets.get("default_lon", FALLBACK_LON)),
        }
    return {
        "athlete_id": os.environ["INTERVALS_ATHLETE_ID"],
        "api_key": os.environ["INTERVALS_API_KEY"],
        "activities_dir": os.environ["INTERVALS_ACTIVITIES_DIR"],
        "weekly_dir": os.environ["INTERVALS_WEEKLY_DIR"],
        "default_lat": float(os.environ.get("INTERVALS_DEFAULT_LAT", FALLBACK_LAT)),
        "default_lon": float(os.environ.get("INTERVALS_DEFAULT_LON", FALLBACK_LON)),
    }


INTERVALS_API_URL = "https://intervals.icu/api/v1"
_settings = _load_settings()
ATHLETE_ID = _settings["athlete_id"]
API_KEY = _settings["api_key"]
ACTIVITIES_DIR = _settings["activities_dir"]
WEEKLY_DIR = _settings["weekly_dir"]
DEFAULT_LAT = _settings["default_lat"]
DEFAULT_LON = _settings["default_lon"]

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
