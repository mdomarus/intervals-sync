from typing import Any, cast

from intervals_sync.notes import activity_note
from intervals_sync.state import Activity


def _minimal_activity(**overrides: Any) -> Activity:
    data: dict[str, Any] = {
        "id": 123,
        "type": "Run",
        "name": "Morning Run",
        "start_date_local": "2026-07-18T08:00:00",
    }
    data.update(overrides)
    return cast(Activity, data)


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
