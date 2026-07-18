import json
import os


def _load_secrets() -> tuple[str, str, str, str]:
    """Load credentials from gitignored secrets.json next to the package
    (fallback: env vars INTERVALS_ATHLETE_ID / INTERVALS_API_KEY / …)."""
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
