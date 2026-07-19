from typing import Any, cast

from intervals_sync.notes import _distance_or_zero, activity_note, week_summary
from intervals_sync.state import Activity, WellnessSeries
from intervals_sync.units import PaceUnit, UnitPreferences, UnitSystem

_METRIC = UnitPreferences(UnitSystem.METRIC, {})
_IMPERIAL_RUN = UnitPreferences(UnitSystem.IMPERIAL, {"Run": PaceUnit.MINS_MILE})


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
        activities = [_week_activity()]
        summary = week_summary(activities, 2026, 29, _METRIC)
        summary_explicit_none = week_summary(activities, 2026, 29, _METRIC, None)
        assert summary is not None
        assert "## Load & trend" not in summary
        # Backward-compat: omitting wellness_series is byte-identical to passing
        # None, and neither introduces the section or trailing artifacts.
        assert summary == summary_explicit_none

    def test_load_section_present_with_wellness(self) -> None:
        series: WellnessSeries = [
            {"id": "2026-07-12", "ctl": 36.0, "atl": 32.0, "atlLoad": 358.0},
            {"id": "2026-07-15", "ctl": 37.0, "atl": 45.0, "atlLoad": 60.0},
            {"id": "2026-07-19", "ctl": 38.0, "atl": 42.0, "atlLoad": 100.0},
        ]
        summary = week_summary([_week_activity()], 2026, 29, _METRIC, series)
        assert summary is not None
        assert "## Load & trend" in summary
        assert summary.index("## Load & trend") < summary.index("## By type")


class TestActivityNoteGapAndThreshold:
    def test_gap_row_present_for_run(self) -> None:
        # gap = 3.5 m/s → 1000/3.5 ≈ 285.7s → 4:45 /km
        note = activity_note(_minimal_activity(type="Run", gap=3.5), _METRIC)
        assert "**GAP:**" in note

    def test_gap_row_absent_without_gap(self) -> None:
        note = activity_note(_minimal_activity(type="Run"), _METRIC)
        assert "**GAP:**" not in note

    def test_gap_row_absent_for_non_run(self) -> None:
        note = activity_note(_minimal_activity(type="Ride", gap=3.5), _METRIC)
        assert "**GAP:**" not in note

    def test_threshold_row_present_for_run(self) -> None:
        note = activity_note(_minimal_activity(type="Run", threshold_pace=3.8), _METRIC)
        assert "**Threshold:**" in note

    def test_threshold_row_absent_for_non_run(self) -> None:
        note = activity_note(
            _minimal_activity(type="Ride", threshold_pace=3.8), _METRIC
        )
        assert "**Threshold:**" not in note

    def test_gap_value_formatted_as_pace(self) -> None:
        # gap = 1000/305 m/s → format_pace(1000, 305) → "5:05 /km"
        note = activity_note(_minimal_activity(type="Run", gap=1000 / 305), _METRIC)
        assert "5:05 /km" in note


class TestActivityNotePaceZones:
    def test_pace_zones_section_present_for_run_with_data(self) -> None:
        note = activity_note(
            _minimal_activity(
                type="Run",
                pace_zone_times=[600, 1800, 0],
                pace_zones=[3.0, 3.5, 4.0],
            ),
            _METRIC,
        )
        assert "## Pace Zones" in note
        assert "| Zone | Up to | Pace time | Pace % |" in note

    def test_gap_columns_present_when_gap_zone_times_available(self) -> None:
        note = activity_note(
            _minimal_activity(
                type="Run",
                pace_zone_times=[600, 1800],
                gap_zone_times=[400, 2000],
                pace_zones=[3.0, 3.5],
            ),
            _METRIC,
        )
        assert "| GAP time | GAP % |" in note

    def test_gap_columns_absent_without_gap_zone_times(self) -> None:
        note = activity_note(
            _minimal_activity(
                type="Run",
                pace_zone_times=[600, 1800],
                pace_zones=[3.0, 3.5],
            ),
            _METRIC,
        )
        assert "| GAP time | GAP % |" not in note

    def test_pace_zones_section_absent_for_non_run(self) -> None:
        note = activity_note(
            _minimal_activity(
                type="Ride",
                pace_zone_times=[600, 1800],
                pace_zones=[3.0, 3.5],
            ),
            _METRIC,
        )
        assert "## Pace Zones" not in note

    def test_pace_zones_section_absent_without_zone_data(self) -> None:
        note = activity_note(_minimal_activity(type="Run"), _METRIC)
        assert "## Pace Zones" not in note

    def test_pace_zones_section_before_power_section(self) -> None:
        note = activity_note(
            _minimal_activity(
                type="Run",
                pace_zone_times=[600, 1800],
                pace_zones=[3.0, 3.5],
                icu_average_watts=250,
                icu_weighted_avg_watts=260,
            ),
            _METRIC,
        )
        assert note.index("## Pace Zones") < note.index("## Power")


class TestActivityNoteTags:
    def test_known_type_appears_in_tags(self) -> None:
        note = activity_note(_minimal_activity(type="Run"), _METRIC)
        assert "tags: [sport, activity, run]" in note

    def test_unknown_type_not_appended_to_tags(self) -> None:
        note = activity_note(_minimal_activity(type=None), _METRIC)
        assert "unknown" not in note
        assert "tags: [sport, activity]" in note

    def test_race_tag_appended_when_race_true(self) -> None:
        note = activity_note(_minimal_activity(race=True), _METRIC)
        assert "race" in note


class TestActivityNoteImperial:
    def test_run_note_uses_miles_and_min_per_mile(self) -> None:
        activity: Activity = cast(
            Activity,
            {
                "type": "Run",
                "id": "1",
                "name": "Morning Run",
                "start_date_local": "2026-07-16T07:00:00",
                "distance": 10000,
                "moving_time": 3000,
                "total_elevation_gain": 120,
            },
        )
        note = activity_note(activity, _IMPERIAL_RUN)
        assert "6.21 mi" in note  # 10000 m
        assert "/mi" in note
        assert "394 ft" in note  # 120 m
        assert "°C" in note or "Conditions" not in note  # temp stays Celsius


class TestDistanceOrZeroHelper:
    """Unit tests for the _distance_or_zero helper for both unit systems."""

    def test_nonzero_metric_returns_km_string(self) -> None:
        assert _distance_or_zero(10000.0, UnitSystem.METRIC) == "10.00 km"

    def test_nonzero_imperial_returns_miles_string(self) -> None:
        result = _distance_or_zero(10000.0, UnitSystem.IMPERIAL)
        assert result == "6.21 mi"

    def test_zero_metric_returns_zero_km(self) -> None:
        assert _distance_or_zero(0.0, UnitSystem.METRIC) == "0.00 km"

    def test_zero_imperial_returns_zero_miles(self) -> None:
        assert _distance_or_zero(0.0, UnitSystem.IMPERIAL) == "0.00 mi"


class TestWeekSummaryImperialZeroDistance:
    """Imperial week_summary with a zero-distance activity renders '0.00 mi', not '0.00 km'."""

    def _weight_training_activity(self) -> Activity:
        """WeightTraining activity with no distance — triggers the zero-distance path."""
        return cast(
            Activity,
            {
                "id": 42,
                "type": "WeightTraining",
                "name": "Strength",
                "start_date_local": "2026-07-15T09:00:00",
                "distance": 0,
                "moving_time": 3600,
                "icu_training_load": 40,
            },
        )

    def test_totals_distance_uses_imperial_zero(self) -> None:
        imperial_prefs = UnitPreferences(UnitSystem.IMPERIAL, {})
        summary = week_summary(
            [self._weight_training_activity()], 2026, 29, imperial_prefs
        )
        assert summary is not None
        assert "0.00 mi" in summary
        assert "0.00 km" not in summary

    def test_by_type_distance_uses_imperial_zero(self) -> None:
        imperial_prefs = UnitPreferences(UnitSystem.IMPERIAL, {})
        summary = week_summary(
            [self._weight_training_activity()], 2026, 29, imperial_prefs
        )
        assert summary is not None
        # The "By type" line for WeightTraining should also use miles
        by_type_section_start = summary.index("## By type")
        by_type_section = summary[by_type_section_start:]
        assert "0.00 mi" in by_type_section
        assert "0.00 km" not in by_type_section

    def test_activities_list_uses_imperial_zero(self) -> None:
        imperial_prefs = UnitPreferences(UnitSystem.IMPERIAL, {})
        summary = week_summary(
            [self._weight_training_activity()], 2026, 29, imperial_prefs
        )
        assert summary is not None
        activities_section_start = summary.index("## Activities")
        activities_section = summary[activities_section_start:]
        assert "0.00 mi" in activities_section
        assert "0.00 km" not in activities_section
