from typing import Any

import intervals_sync.api as api


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
