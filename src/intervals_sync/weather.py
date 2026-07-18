import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from .config import HTTP_TIMEOUT_SECONDS, WEATHER_MAX_PAST_DAYS


def fetch_weather(lat: float, lon: float, start_iso: str) -> dict[str, float] | None:
    """Open-Meteo forecast API with past_days — works for today and up to 92 days back."""
    try:
        start_dt = (
            datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            if "T" in start_iso
            else datetime.strptime(start_iso[:10], "%Y-%m-%d")
        )
        start_dt_naive = start_dt.replace(tzinfo=None)
        days_back = max(1, (datetime.now() - start_dt_naive).days + 1)
        if days_back > WEATHER_MAX_PAST_DAYS:
            return None
        params = urllib.parse.urlencode(
            {
                "latitude": f"{lat:.4f}",
                "longitude": f"{lon:.4f}",
                "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m,temperature_2m",
                "wind_speed_unit": "kmh",
                "timezone": "auto",
                "past_days": days_back,
                "forecast_days": 1,
            }
        )
        url = f"https://api.open-meteo.com/v1/forecast?{params}"
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            weather_payload = json.loads(resp.read())
        hourly = weather_payload.get("hourly", {})
        times = hourly.get("time", [])
        target = start_dt.strftime("%Y-%m-%dT%H:00")
        idx = next(
            (idx for idx, timestamp in enumerate(times) if timestamp == target), None
        )
        if idx is None:
            return None
        return {
            "wind_speed": hourly["wind_speed_10m"][idx],
            "wind_dir": hourly["wind_direction_10m"][idx],
            "wind_gust": hourly["wind_gusts_10m"][idx],
            "temp": hourly["temperature_2m"][idx],
        }
    except (
        ValueError,  # bad date string / non-numeric coordinate
        urllib.error.URLError,  # network failure / timeout
        json.JSONDecodeError,  # malformed response body
        KeyError,  # expected hourly field absent
        IndexError,  # matched time index out of range
    ) as error:
        print(f"  ⚠️  weather fetch failed: {error}")
        return None
