from typing import Any

from intervals_sync.formatters import (
    format_cadence,
    format_duration,
    format_zone_time,
    hr_zones_table,
    iso_year_week,
    pace_zones_table,
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


class TestFormatZoneTime:
    def test_formats_sub_minute_without_dropping_seconds(self) -> None:
        # Regression: 55s used to render as "0min"; it must keep the seconds.
        assert format_zone_time(55) == "0:55"

    def test_formats_minutes_and_seconds(self) -> None:
        assert format_zone_time(1771) == "29:31"

    def test_pads_seconds(self) -> None:
        assert format_zone_time(65) == "1:05"

    def test_formats_hours_when_over_an_hour(self) -> None:
        assert format_zone_time(3900) == "1:05:00"


class TestPaceZonesTable:
    # intervals.icu `pace_zones` are percentages of the athlete's threshold pace
    # (100% == threshold), not absolute speeds. threshold_pace is m/s.
    THRESHOLD_MPS = 3.5335689  # ≈ 4:43 /km, a real intervals.icu run value

    def test_returns_empty_without_data(self) -> None:
        assert (
            pace_zones_table(None, None, None, self.THRESHOLD_MPS, PaceUnit.MINS_KM)
            == []
        )
        assert pace_zones_table([], [], [], self.THRESHOLD_MPS, PaceUnit.MINS_KM) == []

    def test_returns_empty_when_all_zero(self) -> None:
        assert (
            pace_zones_table(
                [0, 0], [0, 0], [77.5, 100.0], self.THRESHOLD_MPS, PaceUnit.MINS_KM
            )
            == []
        )

    def test_builds_combined_pace_and_gap_table(self) -> None:
        # 77.5% of 3.5335689 m/s = 2.739 m/s → 6:05 /km; 100.0% → 4:43 /km.
        table = pace_zones_table(
            [600, 1800],
            [1200, 1200],
            [77.5, 100.0],
            self.THRESHOLD_MPS,
            PaceUnit.MINS_KM,
        )
        assert table == [
            "| Zone | Up to | Pace time | Pace % | GAP time | GAP % |",
            "|:-----|-----:|----------:|-------:|---------:|------:|",
            "| Z1 | 6:05 /km | 10:00 | 25% | 20:00 | 50% |",
            "| Z2 | 4:43 /km | 30:00 | 75% | 20:00 | 50% |",
        ]

    def test_open_top_zone_has_no_threshold(self) -> None:
        # 999.0 is intervals.icu's open-ended top-zone sentinel: no upper pace bound.
        table = pace_zones_table(
            [600, 1800],
            [600, 1800],
            [100.0, 999.0],
            self.THRESHOLD_MPS,
            PaceUnit.MINS_KM,
        )
        assert table[3] == "| Z2 | — | 30:00 | 75% | 30:00 | 75% |"

    def test_skips_zones_with_no_time_in_either_series(self) -> None:
        table = pace_zones_table(
            [0, 1800, 600],
            [0, 1200, 1200],
            [77.5, 94.3, 100.0],
            self.THRESHOLD_MPS,
            PaceUnit.MINS_KM,
        )
        rows = [row for row in table if row.startswith(("| Z1", "| Z2", "| Z3"))]
        assert rows == [
            "| Z2 | 5:00 /km | 30:00 | 75% | 20:00 | 50% |",
            "| Z3 | 4:43 /km | 10:00 | 25% | 20:00 | 50% |",
        ]

    def test_renders_dash_for_zero_time_in_one_series(self) -> None:
        table = pace_zones_table(
            [600, 0],
            [0, 1800],
            [77.5, 100.0],
            self.THRESHOLD_MPS,
            PaceUnit.MINS_KM,
        )
        assert table[2] == "| Z1 | 6:05 /km | 10:00 | 100% | — | — |"
        assert table[3] == "| Z2 | 4:43 /km | — | — | 30:00 | 100% |"

    def test_omits_gap_columns_when_gap_absent(self) -> None:
        table = pace_zones_table(
            [600, 1800], None, [77.5, 100.0], self.THRESHOLD_MPS, PaceUnit.MINS_KM
        )
        assert table == [
            "| Zone | Up to | Pace time | Pace % |",
            "|:-----|-----:|----------:|-------:|",
            "| Z1 | 6:05 /km | 10:00 | 25% |",
            "| Z2 | 4:43 /km | 30:00 | 75% |",
        ]

    def test_no_threshold_column_values_without_threshold(self) -> None:
        table = pace_zones_table(
            [600, 1800], None, [77.5, 100.0], None, PaceUnit.MINS_KM
        )
        assert table[2] == "| Z1 | — | 10:00 | 25% |"


class TestHrZonesTable:
    def test_returns_empty_without_data(self) -> None:
        assert hr_zones_table(None, None) == []
        assert hr_zones_table([], []) == []

    def test_returns_empty_when_all_zero(self) -> None:
        assert hr_zones_table([0, 0], [100, 150]) == []

    def test_builds_table_with_lower_bounds(self) -> None:
        table = hr_zones_table([600, 1800], [120, 150])
        assert table == [
            "| Zone | From | Time | % |",
            "|:-----|-----:|-----:|--:|",
            "| Z1 | 120+ bpm | 10:00 | 25% |",
            "| Z2 | 150+ bpm | 30:00 | 75% |",
        ]

    def test_skips_zero_time_zones(self) -> None:
        table = hr_zones_table([0, 1800, 600], [113, 137, 155])
        rows = [row for row in table if row.startswith(("| Z1", "| Z2", "| Z3"))]
        assert rows == [
            "| Z2 | 137+ bpm | 30:00 | 75% |",
            "| Z3 | 155+ bpm | 10:00 | 25% |",
        ]

    def test_keeps_sub_minute_seconds(self) -> None:
        # 55s must render as 0:55, not the misleading "0min".
        table = hr_zones_table([55, 3345], [120, 150])
        assert table[2] == "| Z1 | 120+ bpm | 0:55 | 2% |"


class TestFormatCadence:
    def test_doubles_single_leg_for_run(self) -> None:
        # intervals.icu reports one leg; running convention is total steps/min.
        assert format_cadence(81.25, "Run") == "162 spm"

    def test_doubles_for_trail_run(self) -> None:
        assert format_cadence(90.0, "TrailRun") == "180 spm"

    def test_keeps_rpm_for_ride(self) -> None:
        assert format_cadence(88.0, "Ride") == "88 rpm"

    def test_returns_none_when_absent(self) -> None:
        assert format_cadence(None, "Run") is None
        assert format_cadence(0, "Run") is None


class TestSplitsTable:
    def _intervals(self) -> dict[str, Any]:
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
