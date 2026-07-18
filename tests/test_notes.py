from typing import Any, cast

from intervals_sync.notes import activity_note, week_summary
from intervals_sync.state import Activity, WellnessSeries


def _minimal_activity(**overrides: Any) -> Activity:
    data: dict[str, Any] = {
        "id": 123,
        "type": "Run",
        "name": "Morning Run",
        "start_date_local": "2026-07-18T08:00:00",
    }
    data.update(overrides)
    return cast(Activity, data)


def _week_activity(**overrides: Any) -> Activity:
    base: dict[str, Any] = {
        "id": 1,
        "type": "Run",
        "name": "W29 Run",
        "start_date_local": "2026-07-15T08:00:00",
        "distance": 10000,
        "moving_time": 3000,
        "icu_training_load": 60,
    }
    base.update(overrides)
    return cast(Activity, base)


class TestWeekSummaryLoadSection:
    def test_no_load_section_without_wellness(self) -> None:
        summary = week_summary([_week_activity()], 2026, 29)
        assert summary is not None
        assert "## Load & trend" not in summary

    def test_load_section_present_with_wellness(self) -> None:
        series: WellnessSeries = [
            {"id": "2026-07-12", "ctl": 36.0, "atl": 32.0, "atlLoad": 358.0},
            {"id": "2026-07-15", "ctl": 37.0, "atl": 45.0, "atlLoad": 60.0},
            {"id": "2026-07-19", "ctl": 38.0, "atl": 42.0, "atlLoad": 100.0},
        ]
        summary = week_summary([_week_activity()], 2026, 29, series)
        assert summary is not None
        assert "## Load & trend" in summary
        assert summary.index("## Load & trend") < summary.index("## By type")


class TestActivityNoteTags:
    def test_known_type_appears_in_tags(self) -> None:
        note = activity_note(_minimal_activity(type="Run"))
        assert "tags: [sport, activity, run]" in note

    def test_unknown_type_not_appended_to_tags(self) -> None:
        note = activity_note(_minimal_activity(type=None))
        assert "unknown" not in note
        assert "tags: [sport, activity]" in note

    def test_race_tag_appended_when_race_true(self) -> None:
        note = activity_note(_minimal_activity(race=True))
        assert "race" in note
