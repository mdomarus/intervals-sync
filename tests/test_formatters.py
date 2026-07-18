from intervals_sync.formatters import (
    format_duration,
    format_pace,
    hr_zones_summary,
    iso_year_week,
    mps_to_kmh,
    sanitize_filename,
)


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


class TestFormatPace:
    def test_computes_pace_per_kilometer(self) -> None:
        # 10 km in 3000 s → 5:00 /km
        assert format_pace(10_000, 3000) == "5:00 /km"

    def test_pads_seconds(self) -> None:
        # 1 km in 305 s → 5:05 /km
        assert format_pace(1000, 305) == "5:05 /km"

    def test_missing_inputs_return_none(self) -> None:
        assert format_pace(None, 3000) is None
        assert format_pace(10_000, None) is None
        assert format_pace(0, 3000) is None


class TestMpsToKmh:
    def test_converts_and_rounds(self) -> None:
        assert mps_to_kmh(10) == 36.0
        assert mps_to_kmh(2.777) == 10.0

    def test_none_returns_none(self) -> None:
        assert mps_to_kmh(None) is None

    def test_zero_converts_to_zero(self) -> None:
        # 0.0 m/s is a valid reading; should convert to 0.0 km/h, not be treated as absent
        assert mps_to_kmh(0) == 0.0


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


class TestHrZonesSummary:
    def test_returns_none_without_data(self) -> None:
        assert hr_zones_summary(None, None) is None
        assert hr_zones_summary([], []) is None

    def test_returns_none_when_all_zero(self) -> None:
        assert hr_zones_summary([0, 0], [100, 150]) is None

    def test_summarizes_active_zones_with_percentages(self) -> None:
        summary = hr_zones_summary([600, 1800], [120, 150])
        assert summary == "Z1 (120+bpm): 10min (25%) | Z2 (150+bpm): 30min (75%)"
