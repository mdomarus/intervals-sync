import urllib.error
from typing import Any
from unittest import mock

from intervals_sync import api
from intervals_sync.config import Settings

_FAKE_SETTINGS: Settings = {
    "athlete_id": "i123",
    "api_key": "key",
    "activities_dir": "/tmp/acts",
    "weekly_dir": "/tmp/weekly",
    "default_lat": 0.0,
    "default_lon": 0.0,
}


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
