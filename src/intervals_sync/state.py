import json
import os
from typing import Any, TypedDict

STATE_FILE = os.path.expanduser("~/.intervals_sync_state.json")


class Activity(TypedDict, total=False):
    id: str
    type: str
    name: str
    start_date_local: str
    distance: float
    moving_time: int
    elapsed_time: int
    total_elevation_gain: float
    total_elevation_loss: float
    average_altitude: float
    min_altitude: float
    max_altitude: float
    average_heartrate: int
    max_heartrate: int
    icu_resting_hr: int
    athlete_max_hr: int
    lthr: int
    icu_hr_zone_times: list[int]
    icu_hr_zones: list[int]
    average_cadence: float
    icu_average_watts: int
    icu_weighted_avg_watts: int
    icu_ftp: int
    icu_intensity: float
    icu_variability_index: float
    decoupling: float
    icu_efficiency_factor: float
    polarization_index: float
    icu_ctl: float
    icu_atl: float
    icu_training_load: int
    trimp: float
    hr_load: int
    # suffer_score is not in the official API schema; passed through for Strava-synced activities
    suffer_score: float
    icu_rpe: int
    session_rpe: int
    perceived_exertion: float
    feel: int
    average_temp: float
    min_temp: int
    max_temp: int
    calories: int
    icu_weight: float
    device_name: str
    source: str
    strava_id: str
    race: bool
    description: str
    tags: list[str]
    icu_warmup_time: int
    icu_cooldown_time: int
    interval_summary: list[Any]
    average_speed: float
    max_speed: float
    use_elevation_correction: bool
    gap: float
    gap_model: str
    pace: float
    threshold_pace: float
    pace_zones: list[float]
    pace_zone_times: list[int]
    gap_zone_times: list[int]


class WellnessDay(TypedDict, total=False):
    id: str  # day, "YYYY-MM-DD"
    ctl: float
    atl: float
    atlLoad: float
    rampRate: float


WellnessSeries = list[WellnessDay]


class State(TypedDict):
    last_sync: str | None


def load_state() -> State:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Corrupt state file {STATE_FILE}: {e}") from e
    return {"last_sync": None}


def save_state(state: State) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
