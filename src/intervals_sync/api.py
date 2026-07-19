import base64
import http.client
import json
import urllib.error
import urllib.request
from typing import Any, cast

from .config import HTTP_TIMEOUT_SECONDS, INTERVALS_API_URL, get_settings
from .state import Activity, Athlete, WellnessSeries


def get_headers() -> dict[str, str]:
    api_key = get_settings()["api_key"]
    creds: str = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 intervals-sync",
    }


def _request(method: str, url: str, body: dict | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    headers = get_headers()
    if data is not None:
        headers = {**headers, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read())


def api_get(path: str) -> Any:
    athlete_id = get_settings()["athlete_id"]
    return _request("GET", f"{INTERVALS_API_URL}/athlete/{athlete_id}/{path}")


def get_activity(act_id: str) -> Activity | None:
    """Fetch a fresh single activity record (e.g. after server-side settings change)."""
    try:
        return cast(Activity, _request("GET", f"{INTERVALS_API_URL}/activity/{act_id}"))
    except (
        urllib.error.URLError,
        http.client.IncompleteRead,
        json.JSONDecodeError,
    ) as e:
        print(f"  ⚠️  activity refetch failed for {act_id}: {e}")
        return None


def get_athlete() -> Athlete | None:
    """Fetch the athlete profile (measurement_preference + sportSettings) used to
    resolve display units. Returns None on network/parse failure so the caller
    falls back to metric instead of aborting the sync."""
    athlete_id = get_settings()["athlete_id"]
    try:
        return cast(
            Athlete, _request("GET", f"{INTERVALS_API_URL}/athlete/{athlete_id}")
        )
    except (
        urllib.error.URLError,
        http.client.IncompleteRead,
        json.JSONDecodeError,
    ) as athlete_error:
        print(f"  ⚠️  athlete profile fetch failed, using metric: {athlete_error}")
        return None


def set_elevation_correction(act_id: str, value: bool) -> bool:
    """Enable/disable elevation correction (DEM) on intervals.icu. Disabled = device
    barometer — consistent with Strava/Garmin. Returns True on success. After PUT the
    server recalculates total_elevation_gain asynchronously."""
    try:
        _request(
            "PUT",
            f"{INTERVALS_API_URL}/activity/{act_id}",
            {"use_elevation_correction": value},
        )
        return True
    except (
        urllib.error.URLError,
        http.client.IncompleteRead,
        json.JSONDecodeError,
    ) as e:
        print(f"  ⚠️  failed to set elevation_correction for {act_id}: {e}")
        return False


def fetch_intervals(act_id: str) -> dict[str, Any] | None:
    """Fetch detailed splits (WORK/RECOVERY) for an activity."""
    try:
        return _request("GET", f"{INTERVALS_API_URL}/activity/{act_id}/intervals")
    except (
        urllib.error.URLError,
        http.client.IncompleteRead,
        json.JSONDecodeError,
    ) as e:
        print(f"  ⚠️  intervals fetch failed for {act_id}: {e}")
        return None


def fetch_activity_midpoint(act_id: str) -> tuple[float, float] | None:
    """Representative GPS location of an activity: the point nearest its time
    middle, taken from the latlng stream (data = latitudes, data2 = longitudes,
    matched by index). For long point-to-point rides/runs this is more
    representative than the start, which is what the weather lookup wants.

    Searches outward from the middle index to skip GPS drop-outs (None samples).
    Returns None for GPS-less activities (indoor: empty stream) or a stream with
    no usable fix, so the caller can omit weather rather than guess a location."""
    try:
        streams = _request(
            "GET", f"{INTERVALS_API_URL}/activity/{act_id}/streams?types=latlng"
        )
    except (
        urllib.error.URLError,
        http.client.IncompleteRead,
        json.JSONDecodeError,
    ) as e:
        print(f"  ⚠️  latlng stream fetch failed for {act_id}: {e}")
        return None

    latlng_stream = next(
        (stream for stream in streams if stream.get("type") == "latlng"), None
    )
    if latlng_stream is None:
        return None
    latitudes = latlng_stream.get("data") or []
    longitudes = latlng_stream.get("data2") or []
    sample_count = min(len(latitudes), len(longitudes))
    if sample_count == 0:
        return None

    middle = sample_count // 2
    for offset in range(sample_count):
        for index in (middle + offset, middle - offset):
            if 0 <= index < sample_count:
                latitude = latitudes[index]
                longitude = longitudes[index]
                if latitude is not None and longitude is not None:
                    return (latitude, longitude)
    return None


def fetch_wellness(oldest: str, newest: str) -> WellnessSeries | None:
    """Daily wellness rows (CTL/ATL/atlLoad per day) for the date range.

    Returns None on network/parse failure so the caller can render weekly
    summaries without the load section instead of aborting the sync."""
    try:
        return cast(
            WellnessSeries, api_get(f"wellness?oldest={oldest}&newest={newest}")
        )
    except (
        urllib.error.URLError,
        http.client.IncompleteRead,
        json.JSONDecodeError,
    ) as wellness_error:
        print(f"  ⚠️  wellness fetch failed: {wellness_error}")
        return None
