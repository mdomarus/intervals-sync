import urllib.error
from collections.abc import Sequence
from typing import Any
from unittest import mock

from intervals_sync import api
from intervals_sync.config import Settings

_FAKE_SETTINGS: Settings = {
    "athlete_id": "i123",
    "api_key": "key",
    "activities_dir": "/tmp/acts",
    "weekly_dir": "/tmp/weekly",
}


def _latlng_stream(
    lats: Sequence[float | None], lons: Sequence[float | None]
) -> list[dict]:
    """Shape a intervals.icu latlng stream response: parallel data (lat) and
    data2 (lon) arrays, matched by index."""
    return [{"type": "latlng", "data": lats, "data2": lons}]


class TestGetAthlete:
    def test_returns_profile_on_success(self) -> None:
        profile = {"id": "i123", "measurement_preference": "IMPERIAL"}
        with (
            mock.patch.object(api, "get_settings", return_value=_FAKE_SETTINGS),
            mock.patch.object(api, "_request", return_value=profile),
        ):
            assert api.get_athlete() == profile

    def test_returns_none_on_network_error(self) -> None:
        with (
            mock.patch.object(api, "get_settings", return_value=_FAKE_SETTINGS),
            mock.patch.object(
                api, "_request", side_effect=urllib.error.URLError("down")
            ),
        ):
            assert api.get_athlete() is None


class TestFetchActivityMidpoint:
    def test_returns_point_nearest_the_time_middle(self) -> None:
        # Middle index (2) has a valid fix — used as the activity's representative
        # location (roughly mid-way through time for an evenly sampled stream).
        lats = [54.60, 54.61, 54.62, 54.63, 54.64]
        lons = [18.30, 18.31, 18.32, 18.33, 18.34]
        with (
            mock.patch.object(api, "get_settings", return_value=_FAKE_SETTINGS),
            mock.patch.object(api, "_request", return_value=_latlng_stream(lats, lons)),
        ):
            assert api.fetch_activity_midpoint("i1") == (54.62, 18.32)

    def test_searches_outward_when_middle_is_a_gps_gap(self) -> None:
        # Middle sample is a GPS drop-out (None) — fall back to the nearest
        # index on either side that has both coordinates.
        lats = [54.60, 54.61, None, 54.63, 54.64]
        lons = [18.30, 18.31, None, 18.33, 18.34]
        with (
            mock.patch.object(api, "get_settings", return_value=_FAKE_SETTINGS),
            mock.patch.object(api, "_request", return_value=_latlng_stream(lats, lons)),
        ):
            assert api.fetch_activity_midpoint("i1") == (54.63, 18.33)

    def test_returns_none_when_stream_is_all_gaps(self) -> None:
        with (
            mock.patch.object(api, "get_settings", return_value=_FAKE_SETTINGS),
            mock.patch.object(
                api,
                "_request",
                return_value=_latlng_stream([None, None], [None, None]),
            ),
        ):
            assert api.fetch_activity_midpoint("i1") is None

    def test_returns_none_when_no_latlng_stream(self) -> None:
        # Indoor / GPS-less activity: intervals.icu returns an empty stream list.
        with (
            mock.patch.object(api, "get_settings", return_value=_FAKE_SETTINGS),
            mock.patch.object(api, "_request", return_value=[]),
        ):
            assert api.fetch_activity_midpoint("i1") is None

    def test_returns_none_on_network_error(self) -> None:
        with (
            mock.patch.object(api, "get_settings", return_value=_FAKE_SETTINGS),
            mock.patch.object(
                api, "_request", side_effect=urllib.error.URLError("down")
            ),
        ):
            assert api.fetch_activity_midpoint("i1") is None


class TestFetchWellness:
    def test_returns_rows_and_builds_wellness_path(self, monkeypatch: Any) -> None:
        captured: dict[str, str] = {}

        def fake_api_get(path: str) -> Any:
            captured["path"] = path
            return [{"id": "2026-07-19", "ctl": 38.0, "atl": 30.0, "atlLoad": 100.0}]

        monkeypatch.setattr(api, "api_get", fake_api_get)
        rows = api.fetch_wellness("2026-06-01", "2026-07-19")
        assert rows is not None and rows[0]["id"] == "2026-07-19"
        assert captured["path"] == "wellness?oldest=2026-06-01&newest=2026-07-19"

    def test_returns_none_on_url_error(self, monkeypatch: Any) -> None:
        import urllib.error

        def raising_api_get(path: str) -> Any:
            raise urllib.error.URLError("no network")

        monkeypatch.setattr(api, "api_get", raising_api_get)
        assert api.fetch_wellness("2026-06-01", "2026-07-19") is None
