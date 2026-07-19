from intervals_sync.units import (
    PaceUnit,
    UnitSystem,
    format_distance,
    format_elevation,
    format_pace,
    format_speed,
)


class TestFormatDistance:
    def test_metric_shows_kilometers(self) -> None:
        assert format_distance(5000, UnitSystem.METRIC) == "5.00 km"

    def test_imperial_shows_miles(self) -> None:
        # 5000 m / 1609.344 = 3.107 mi → 3.11 mi
        assert format_distance(5000, UnitSystem.IMPERIAL) == "3.11 mi"

    def test_zero_and_none_return_none(self) -> None:
        assert format_distance(0, UnitSystem.METRIC) is None
        assert format_distance(None, UnitSystem.METRIC) is None


class TestFormatSpeed:
    def test_metric_shows_kmh(self) -> None:
        assert format_speed(10, UnitSystem.METRIC) == "36.0 km/h"

    def test_imperial_shows_mph(self) -> None:
        # 10 m/s * 2.236936 = 22.36936 → 22.4 mph
        assert format_speed(10, UnitSystem.IMPERIAL) == "22.4 mph"

    def test_zero_converts_not_absent(self) -> None:
        assert format_speed(0, UnitSystem.METRIC) == "0.0 km/h"

    def test_none_returns_none(self) -> None:
        assert format_speed(None, UnitSystem.IMPERIAL) is None


class TestFormatElevation:
    def test_metric_shows_meters(self) -> None:
        assert format_elevation(120, UnitSystem.METRIC) == "120 m"

    def test_imperial_shows_feet(self) -> None:
        # 120 m / 0.3048 = 393.7 ft → 394 ft
        assert format_elevation(120, UnitSystem.IMPERIAL) == "394 ft"

    def test_none_returns_none(self) -> None:
        assert format_elevation(None, UnitSystem.METRIC) is None


class TestFormatPace:
    def test_mins_km(self) -> None:
        assert format_pace(10_000, 3000, PaceUnit.MINS_KM) == "5:00 /km"

    def test_mins_mile(self) -> None:
        # 10000 m in 3000 s = 5:00/km; per mile = 3000 / (10000/1609.344) = 482.8 s → 8:03 /mi
        assert format_pace(10_000, 3000, PaceUnit.MINS_MILE) == "8:03 /mi"

    def test_secs_100m(self) -> None:
        # 1000 m in 1050 s → 105 s per 100 m → 1:45 /100m
        assert format_pace(1000, 1050, PaceUnit.SECS_100M) == "1:45 /100m"

    def test_secs_500m(self) -> None:
        # 2000 m in 480 s → 120 s per 500 m → 2:00 /500m
        assert format_pace(2000, 480, PaceUnit.SECS_500M) == "2:00 /500m"

    def test_none_pace_unit_falls_back_to_km(self) -> None:
        assert format_pace(10_000, 3000, PaceUnit.NONE) == "5:00 /km"

    def test_missing_inputs_return_none(self) -> None:
        assert format_pace(None, 3000, PaceUnit.MINS_KM) is None
        assert format_pace(10_000, None, PaceUnit.MINS_KM) is None
        assert format_pace(0, 3000, PaceUnit.MINS_KM) is None
