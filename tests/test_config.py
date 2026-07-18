import json

import pytest

from intervals_sync import config
from intervals_sync.config import ConfigError


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    """get_settings() is memoized; reset it around every test so each starts
    from a clean load."""
    config.get_settings.cache_clear()


REQUIRED = {
    "athlete_id": "i12345",
    "api_key": "secret-key",
    "activities_dir": "/tmp/activities",
    "weekly_dir": "/tmp/weekly",
}


def test_loads_from_secrets_file(tmp_path, monkeypatch) -> None:
    secrets_path = tmp_path / "secrets.json"
    secrets_path.write_text(json.dumps({**REQUIRED, "default_lat": 50.0}))
    monkeypatch.setattr(config, "_find_secrets_file", lambda: str(secrets_path))

    settings = config.get_settings()

    assert settings["athlete_id"] == "i12345"
    assert settings["default_lat"] == 50.0
    # unspecified coordinate falls back to the module default
    assert settings["default_lon"] == config.FALLBACK_LON


def test_missing_key_in_secrets_raises_config_error(tmp_path, monkeypatch) -> None:
    incomplete = {k: v for k, v in REQUIRED.items() if k != "api_key"}
    secrets_path = tmp_path / "secrets.json"
    secrets_path.write_text(json.dumps(incomplete))
    monkeypatch.setattr(config, "_find_secrets_file", lambda: str(secrets_path))

    with pytest.raises(ConfigError, match="api_key"):
        config.get_settings()


def test_malformed_json_raises_config_error(tmp_path, monkeypatch) -> None:
    secrets_path = tmp_path / "secrets.json"
    secrets_path.write_text("{not valid json")
    monkeypatch.setattr(config, "_find_secrets_file", lambda: str(secrets_path))

    with pytest.raises(ConfigError, match="Invalid JSON"):
        config.get_settings()


def test_falls_back_to_env_vars(monkeypatch) -> None:
    monkeypatch.setattr(config, "_find_secrets_file", lambda: None)
    monkeypatch.setenv("INTERVALS_ATHLETE_ID", "i999")
    monkeypatch.setenv("INTERVALS_API_KEY", "env-key")
    monkeypatch.setenv("INTERVALS_ACTIVITIES_DIR", "/tmp/a")
    monkeypatch.setenv("INTERVALS_WEEKLY_DIR", "/tmp/w")

    settings = config.get_settings()

    assert settings["athlete_id"] == "i999"
    assert settings["api_key"] == "env-key"


def test_missing_env_vars_raise_config_error(monkeypatch) -> None:
    monkeypatch.setattr(config, "_find_secrets_file", lambda: None)
    for env in (
        "INTERVALS_ATHLETE_ID",
        "INTERVALS_API_KEY",
        "INTERVALS_ACTIVITIES_DIR",
        "INTERVALS_WEEKLY_DIR",
    ):
        monkeypatch.delenv(env, raising=False)

    with pytest.raises(ConfigError, match="environment variables"):
        config.get_settings()
