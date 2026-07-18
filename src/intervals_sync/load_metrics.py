from datetime import date, timedelta
from statistics import mean, pstdev
from typing import TypedDict

from .config import (
    ACWR_ELEVATED_MAX,
    ACWR_OPTIMAL_MAX,
    ACWR_UNDERLOAD_MAX,
    LOAD_WOW_DELOAD_PCT,
    LOAD_WOW_JUMP_PCT,
    MONOTONY_GOOD_MAX,
    MONOTONY_MODERATE_MAX,
    RAMP_AGGRESSIVE_MAX,
    RAMP_SAFE_MAX,
    TREND_WEEKS,
)
from .state import WellnessDay, WellnessSeries


def _week_sunday(year: int, week_num: int) -> date:
    """Sunday (ISO weekday 7) of the given ISO week."""
    return date.fromisocalendar(year, week_num, 7)


def _week_reference_row(
    series: WellnessSeries, year: int, week_num: int
) -> WellnessDay | None:
    """Row for the week's Sunday, or the last row on/before it. None if none qualify."""
    sunday_iso = _week_sunday(year, week_num).isoformat()
    candidates = [row for row in series if row.get("id", "") <= sunday_iso]
    if not candidates:
        return None
    return max(candidates, key=lambda row: row.get("id", ""))


def _week_daily_loads(series: WellnessSeries, year: int, week_num: int) -> list[float]:
    """Mon–Sun atlLoad values for the week; missing days count as 0.0."""
    load_by_day = {row.get("id", ""): (row.get("atlLoad") or 0.0) for row in series}
    daily_loads: list[float] = []
    for iso_weekday in range(1, 8):
        day_iso = date.fromisocalendar(year, week_num, iso_weekday).isoformat()
        daily_loads.append(load_by_day.get(day_iso, 0.0))
    return daily_loads


def acwr(series: WellnessSeries, year: int, week_num: int) -> float | None:
    """ATL/CTL at the week's reference row. None if no row or CTL is zero."""
    reference_row = _week_reference_row(series, year, week_num)
    if reference_row is None:
        return None
    chronic_load = reference_row.get("ctl") or 0.0
    acute_load = reference_row.get("atl") or 0.0
    if chronic_load == 0:
        return None
    return round(acute_load / chronic_load, 2)


def acwr_label(value: float) -> str:
    """Interpret ACWR value per Gabbett "sweet spot" bands with emoji indicators."""
    if value < ACWR_UNDERLOAD_MAX:
        return "🟡 detraining / underload"
    if value <= ACWR_OPTIMAL_MAX:
        return "🟢 optimal range"
    if value <= ACWR_ELEVATED_MAX:
        return "🟠 elevated risk — above sweet-spot (0.8–1.3)"
    return "🔴 high injury risk"


def ramp_rate(series: WellnessSeries, year: int, week_num: int) -> float | None:
    """Week-over-week change in CTL. None if either week lacks a reference row."""
    this_week_row = _week_reference_row(series, year, week_num)
    previous_sunday = _week_sunday(year, week_num) - timedelta(days=7)
    previous_iso = previous_sunday.isocalendar()
    previous_week_row = _week_reference_row(series, previous_iso[0], previous_iso[1])
    if this_week_row is None or previous_week_row is None:
        return None
    this_ctl = this_week_row.get("ctl") or 0.0
    previous_ctl = previous_week_row.get("ctl") or 0.0
    return round(this_ctl - previous_ctl, 1)


def ramp_rate_label(value: float) -> str:
    if value > RAMP_AGGRESSIVE_MAX:
        return "🔴 very fast rise"
    if value > RAMP_SAFE_MAX:
        return "🟠 aggressive build"
    if value >= 0:
        return "🟢 safe build"
    return "🔵 detraining / recovery"


def week_over_week_load(
    series: WellnessSeries, year: int, week_num: int
) -> float | None:
    """Percent change in summed weekly load vs the previous week.

    None when the previous week has no load to compare against (avoids
    division by zero and a meaningless "+∞%")."""
    this_week_total = sum(_week_daily_loads(series, year, week_num))
    previous_sunday = _week_sunday(year, week_num) - timedelta(days=7)
    previous_iso = previous_sunday.isocalendar()
    previous_week_total = sum(
        _week_daily_loads(series, previous_iso[0], previous_iso[1])
    )
    if previous_week_total == 0:
        return None
    return round((this_week_total - previous_week_total) / previous_week_total * 100, 0)


def week_over_week_label(percent: float) -> str:
    if percent > LOAD_WOW_JUMP_PCT:
        return "🟠 large jump vs previous week"
    if percent < LOAD_WOW_DELOAD_PCT:
        return "🔵 clear deload"
    return "🟢 normal"


def monotony_and_strain(
    series: WellnessSeries, year: int, week_num: int
) -> tuple[float, float] | None:
    """Foster monotony (mean/pstdev of daily load) and strain (sum × monotony).

    None when daily load has zero spread (all seven days equal, including an
    empty week) — monotony is undefined there."""
    daily_loads = _week_daily_loads(series, year, week_num)
    load_spread = pstdev(daily_loads)
    if load_spread == 0:
        return None
    monotony = mean(daily_loads) / load_spread
    strain = sum(daily_loads) * monotony
    return round(monotony, 2), round(strain, 0)


def monotony_label(value: float) -> str:
    if value > MONOTONY_MODERATE_MAX:
        return "🔴 high"
    if value > MONOTONY_GOOD_MAX:
        return "🟠 moderate"
    return "🟢 good variation"


class TrendRow(TypedDict):
    week: str
    ctl: float
    load: float
    ramp: float | None
    partial: bool


def _last_series_day(series: WellnessSeries) -> str:
    return max((row.get("id", "") for row in series), default="")


def trend_rows(series: WellnessSeries, year: int, week_num: int) -> list[TrendRow]:
    """Up to TREND_WEEKS trailing weekly rows ending at (year, week_num).

    Weeks with no wellness reference row are skipped. A week is 'partial' when
    its Sunday is later than the last day present in the series (mid-week sync)."""
    last_day = _last_series_day(series)
    end_sunday = _week_sunday(year, week_num)
    rows: list[TrendRow] = []
    for weeks_back in range(TREND_WEEKS - 1, -1, -1):
        week_sunday = end_sunday - timedelta(days=7 * weeks_back)
        iso_year, iso_week, _ = week_sunday.isocalendar()
        reference_row = _week_reference_row(series, iso_year, iso_week)
        if reference_row is None:
            continue
        rows.append(
            {
                "week": f"{iso_year}-W{iso_week:02d}",
                "ctl": round(reference_row.get("ctl") or 0.0, 1),
                "load": round(sum(_week_daily_loads(series, iso_year, iso_week)), 0),
                "ramp": ramp_rate(series, iso_year, iso_week),
                "partial": week_sunday.isoformat() > last_day,
            }
        )
    return rows
