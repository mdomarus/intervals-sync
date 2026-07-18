import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime


def fetch_weather(lat: float, lon: float, start_iso: str):
    """Open-Meteo forecast API z past_days — działa dla dzisiaj i do 92 dni wstecz."""
    try:
        start_dt = (
            datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            if "T" in start_iso
            else datetime.strptime(start_iso[:10], "%Y-%m-%d")
        )
        days_back = max(1, (datetime.now() - start_dt).days + 1)
        if days_back > 92:
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
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        target = start_dt.strftime("%Y-%m-%dT%H:00")
        idx = next((i for i, t in enumerate(times) if t == target), None)
        if idx is None:
            return None
        return {
            "wind_speed": hourly["wind_speed_10m"][idx],
            "wind_dir": hourly["wind_direction_10m"][idx],
            "wind_gust": hourly["wind_gusts_10m"][idx],
            "temp": hourly["temperature_2m"][idx],
        }
    except Exception as e:
        print(f"  ⚠ weather fetch failed: {e}")
        return None


def wind_label(course_deg, wind_from_deg):
    """Względny kąt wiatr→kierunek biegu. Wind 'from' = skąd wieje."""
    if course_deg is None or wind_from_deg is None:
        return "—"
    rel = ((course_deg - wind_from_deg + 540) % 360) - 180
    a = abs(rel)
    if a < 30:
        return f"⬆️ head ({a:.0f}°)"
    if a > 150:
        return f"⬇️ tail ({180 - a:.0f}°)"
    side = "↗" if rel > 0 else "↖"
    if a < 60:
        return f"{side} head-cross"
    if a > 120:
        return f"{side} tail-cross"
    return f"{side} cross"
