from datetime import date

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
