import base64
import json
import urllib.request
from typing import Any, cast

from .config import ATHLETE_ID, API_KEY, INTERVALS_API_URL
from .state import Activity


def get_headers() -> dict[str, str]:
    creds: str = base64.b64encode(f"API_KEY:{API_KEY}".encode()).decode()
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
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def api_get(path: str) -> Any:
    return _request("GET", f"{INTERVALS_API_URL}/athlete/{ATHLETE_ID}/{path}")


def get_activity(act_id: str) -> Activity | None:
    """Fetch a fresh single activity record (e.g. after server-side settings change)."""
    try:
        return cast(Activity, _request("GET", f"{INTERVALS_API_URL}/activity/{act_id}"))
    except Exception as e:
        print(f"  ⚠️  activity refetch failed for {act_id}: {e}")
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
    except Exception as e:
        print(f"  ⚠️  failed to set elevation_correction for {act_id}: {e}")
        return False


def fetch_intervals(act_id: str) -> dict | None:
    """Fetch detailed splits (WORK/RECOVERY) for an activity."""
    try:
        return _request("GET", f"{INTERVALS_API_URL}/activity/{act_id}/intervals")
    except Exception as e:
        print(f"  ⚠️  intervals fetch failed for {act_id}: {e}")
        return None
