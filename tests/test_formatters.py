from intervals_sync.formatters import (
    format_duration,
    hr_zones_summary,
    iso_year_week,
    pace_zones_summary,
    sanitize_filename,
    splits_table,
)
from intervals_sync.units import PaceUnit, UnitPreferences, UnitSystem


class TestFormatDuration:
    def test_formats_hours_minutes_seconds(self) -> None:
        assert format_duration(3661) == "1:01:01"

    def test_pads_minutes_and_seconds(self) -> None:
        assert format_duration(65) == "0:01:05"

    def test_accepts_float_seconds(self) -> None:
        assert format_duration(90.9) == "0:01:30"

    def test_zero_and_none_render_as_dash(self) -> None:
        assert format_duration(0) == "—"
        assert format_duration(None) == "—"


class TestIsoYearWeek:
    def test_returns_iso_year_and_week(self) -> None:
        assert iso_year_week("2026-07-16") == (2026, 29)

    def test_week_belongs_to_previous_iso_year(self) -> None:
        # 2021-01-01 is ISO week 53 of 2020
        assert iso_year_week("2021-01-01") == (2020, 53)


class TestSanitizeFilename:
    def test_keeps_alphanumerics_spaces_dashes_underscores(self) -> None:
        assert sanitize_filename("Morning Run - 10km_easy") == "Morning Run - 10km_easy"

    def test_replaces_path_separators(self) -> None:
        assert sanitize_filename("a/b:c") == "a_b_c"

    def test_preserves_standalone_emoji(self) -> None:
        # A base emoji codepoint (Unicode category So) is kept as-is.
        assert sanitize_filename("Trail 🐗 Run") == "Trail 🐗 Run"

    def test_strips_variation_selector(self) -> None:
        # 🏔️ is mountain (U+1F3D4, kept) + variation selector (U+FE0F, category
        # Mn, not kept) → the selector becomes "_". Documents existing behavior
        # that on-disk filenames already rely on.
        assert sanitize_filename("🏔️") == "🏔_"


class TestPaceZonesSummary:
    def test_returns_none_without_data(self) -> None:
        assert pace_zones_summary(None, None, PaceUnit.MINS_KM) is None
        assert pace_zones_summary([], [], PaceUnit.MINS_KM) is None

    def test_returns_none_when_all_zero(self) -> None:
        assert pace_zones_summary([0, 0, 0], [3.0, 3.5, 4.0], PaceUnit.MINS_KM) is None

    def test_formats_zones_with_limits(self) -> None:
        # Z1: 3.0 m/s → 1000/3.0 s/km = 333s → 5:33 /km
        # Z2: 3.5 m/s → 1000/3.5 s/km ≈ 286s → 4:46 /km
        result = pace_zones_summary([600, 1800], [3.0, 3.5], PaceUnit.MINS_KM)
        assert result == "Z1 (<5:33 /km): 10min (25%) | Z2 (<4:46 /km): 30min (75%)"

    def test_formats_zones_in_miles(self) -> None:
        # 3.0 m/s → 1609.344/3.0 = 536.4 s/mi → 8:56 /mi
        # 3.5 m/s → 1609.344/3.5 = 459.8 s/mi → 7:40 /mi
        result = pace_zones_summary([600, 1800], [3.0, 3.5], PaceUnit.MINS_MILE)
        assert result == "Z1 (<8:56 /mi): 10min (25%) | Z2 (<7:40 /mi): 30min (75%)"

    def test_formats_zones_without_limits(self) -> None:
        result = pace_zones_summary([600, 1800], None, PaceUnit.MINS_KM)
        assert result == "Z1: 10min (25%) | Z2: 30min (75%)"

    def test_skips_zero_time_zones(self) -> None:
        result = pace_zones_summary([0, 1800, 600], [3.0, 3.5, 4.0], PaceUnit.MINS_KM)
        assert result == "Z2 (<4:46 /km): 30min (75%) | Z3 (<4:10 /km): 10min (25%)"


class TestHrZonesSummary:
    def test_returns_none_without_data(self) -> None:
        assert hr_zones_summary(None, None) is None
        assert hr_zones_summary([], []) is None

    def test_returns_none_when_all_zero(self) -> None:
        assert hr_zones_summary([0, 0], [100, 150]) is None

    def test_summarizes_active_zones_with_percentages(self) -> None:
        summary = hr_zones_summary([600, 1800], [120, 150])
        assert summary == "Z1 (120+bpm): 10min (25%) | Z2 (150+bpm): 30min (75%)"


class TestSplitsTable:
    def _intervals(self) -> dict:
        return {
            "icu_intervals": [
                {
                    "type": "WORK",
                    "distance": 1000,
                    "moving_time": 300,
                    "gap": 3.4,
                    "average_speed": 3.3,
                }
            ]
        }

    def test_run_splits_metric(self) -> None:
        prefs = UnitPreferences(UnitSystem.METRIC, {})
        rows = "\n".join(splits_table(self._intervals(), "Run", prefs))
        assert "1.00 km" in rows
        assert "5:00 /km" in rows  # 1000 m in 300 s

    def test_run_splits_imperial(self) -> None:
        prefs = UnitPreferences(UnitSystem.IMPERIAL, {"Run": PaceUnit.MINS_MILE})
        rows = "\n".join(splits_table(self._intervals(), "Run", prefs))
        assert "0.62 mi" in rows  # 1000 m ≈ 0.621 mi
        assert "/mi" in rows

    def test_ride_splits_imperial_speed(self) -> None:
        prefs = UnitPreferences(UnitSystem.IMPERIAL, {})
        rows = "\n".join(splits_table(self._intervals(), "Ride", prefs))
        assert "mph" in rows
