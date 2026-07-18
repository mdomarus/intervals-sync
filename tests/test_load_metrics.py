from datetime import date
from statistics import pstdev

from intervals_sync.load_metrics import (
    _week_daily_loads,
    _week_reference_row,
    _week_sunday,
    acwr,
    acwr_label,
    monotony_and_strain,
    monotony_label,
    ramp_rate,
    ramp_rate_label,
    trend_rows,
    week_over_week_label,
    week_over_week_load,
)
from intervals_sync.state import WellnessSeries


def _series(*days: tuple[str, float, float, float]) -> WellnessSeries:
    """Build a wellness series from (id, ctl, atl, atlLoad) tuples."""
    return [
        {"id": day_id, "ctl": ctl, "atl": atl, "atlLoad": load}
        for day_id, ctl, atl, load in days
    ]


class TestWeekLookupHelpers:
    def test_week_sunday_is_iso_day_seven(self) -> None:
        assert _week_sunday(2026, 29) == date(2026, 7, 19)

    def test_reference_row_prefers_exact_sunday(self) -> None:
        series = _series(
            ("2026-07-18", 36.0, 28.0, 0.0),
            ("2026-07-19", 37.0, 30.0, 50.0),
        )
        row = _week_reference_row(series, 2026, 29)
        assert row is not None and row["id"] == "2026-07-19"

    def test_reference_row_falls_back_to_last_day_before_sunday(self) -> None:
        series = _series(("2026-07-15", 35.0, 25.0, 20.0))
        row = _week_reference_row(series, 2026, 29)
        assert row is not None and row["id"] == "2026-07-15"

    def test_reference_row_none_when_series_all_after_sunday(self) -> None:
        series = _series(("2026-07-25", 40.0, 30.0, 0.0))
        assert _week_reference_row(series, 2026, 29) is None

    def test_daily_loads_are_monday_to_sunday_zero_filled(self) -> None:
        series = _series(
            ("2026-07-13", 0.0, 0.0, 82.0),  # Monday of W29
            ("2026-07-16", 0.0, 0.0, 32.0),  # Thursday
        )
        assert _week_daily_loads(series, 2026, 29) == [
            82.0,
            0.0,
            0.0,
            32.0,
            0.0,
            0.0,
            0.0,
        ]


class TestAcwr:
    def test_acwr_is_atl_over_ctl_at_reference_row(self) -> None:
        series = _series(("2026-07-19", 30.0, 42.0, 0.0))
        assert acwr(series, 2026, 29) == 1.4

    def test_acwr_none_when_ctl_zero(self) -> None:
        series = _series(("2026-07-19", 0.0, 10.0, 0.0))
        assert acwr(series, 2026, 29) is None

    def test_acwr_none_when_no_row(self) -> None:
        assert acwr(_series(), 2026, 29) is None

    def test_acwr_label_bands(self) -> None:
        assert "detraining" in acwr_label(0.7)
        assert "optimal" in acwr_label(1.0)
        assert "elevated" in acwr_label(1.4)
        assert "high injury risk" in acwr_label(1.6)


class TestRampRate:
    def test_ramp_is_ctl_delta_week_over_week(self) -> None:
        series = _series(
            ("2026-07-12", 32.0, 30.0, 0.0),  # Sunday W28
            ("2026-07-19", 38.2, 30.0, 0.0),  # Sunday W29
        )
        assert ramp_rate(series, 2026, 29) == 6.2

    def test_ramp_none_without_previous_week(self) -> None:
        series = _series(("2026-07-19", 38.2, 30.0, 0.0))
        assert ramp_rate(series, 2026, 29) is None

    def test_ramp_label_bands(self) -> None:
        assert "very fast" in ramp_rate_label(9.0)
        assert "aggressive" in ramp_rate_label(6.0)
        assert "safe" in ramp_rate_label(3.0)
        assert "detraining" in ramp_rate_label(-1.0)


class TestWeekOverWeekLoad:
    def test_percent_increase_vs_previous_week(self) -> None:
        series = _series(
            ("2026-07-06", 0.0, 0.0, 100.0),  # Monday W28, previous-week total 100
            ("2026-07-13", 0.0, 0.0, 134.0),  # Monday W29, this-week total 134
        )
        assert week_over_week_load(series, 2026, 29) == 34.0

    def test_none_when_previous_week_empty(self) -> None:
        series = _series(("2026-07-13", 0.0, 0.0, 134.0))
        assert week_over_week_load(series, 2026, 29) is None

    def test_label_bands(self) -> None:
        assert "large jump" in week_over_week_label(40.0)
        assert "normal" in week_over_week_label(10.0)
        assert "deload" in week_over_week_label(-40.0)


class TestMonotonyAndStrain:
    def test_single_heavy_day_gives_high_monotony(self) -> None:
        # One heavy day, rest zero → high monotony (spread small relative to mean)
        series = _series(("2026-07-13", 0.0, 0.0, 70.0))
        result = monotony_and_strain(series, 2026, 29)
        assert result is not None
        monotony, strain = result
        expected_monotony = round((70 / 7) / pstdev([70.0, 0, 0, 0, 0, 0, 0]), 2)
        assert monotony == expected_monotony
        assert strain == round(70.0 * expected_monotony, 0)

    def test_none_when_stdev_zero(self) -> None:
        # All seven days equal (including all-zero) → pstdev 0 → undefined monotony
        assert monotony_and_strain(_series(), 2026, 29) is None

    def test_label_bands(self) -> None:
        assert "high" in monotony_label(2.5)
        assert "moderate" in monotony_label(1.7)
        assert "good" in monotony_label(1.0)


class TestTrendRows:
    def test_builds_rows_for_weeks_with_data(self) -> None:
        series = _series(
            ("2026-07-05", 34.0, 30.0, 300.0),  # Sunday W27
            ("2026-07-12", 36.0, 32.0, 358.0),  # Sunday W28
            ("2026-07-19", 38.0, 30.0, 421.0),  # Sunday W29
        )
        rows = trend_rows(series, 2026, 29)
        assert [row["week"] for row in rows] == ["2026-W27", "2026-W28", "2026-W29"]
        assert rows[-1]["ctl"] == 38.0
        assert rows[-1]["ramp"] == 2.0  # 38.0 - 36.0

    def test_partial_flag_when_sunday_beyond_last_series_day(self) -> None:
        series = _series(
            ("2026-07-12", 36.0, 32.0, 358.0),  # Sunday W28 (complete)
            ("2026-07-15", 37.0, 33.0, 60.0),  # Wednesday W29 (week still in progress)
        )
        rows = trend_rows(series, 2026, 29)
        assert rows[-1]["week"] == "2026-W29"
        assert rows[-1]["partial"] is True
        assert rows[-2]["partial"] is False

    def test_skips_weeks_without_data(self) -> None:
        series = _series(("2026-07-19", 38.0, 30.0, 421.0))  # only W29
        rows = trend_rows(series, 2026, 29)
        assert [row["week"] for row in rows] == ["2026-W29"]
