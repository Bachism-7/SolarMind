from datetime import UTC, date, datetime

import pytest

from app.solar import calculate_solar, sample_local_day, validate_coordinates


def test_coordinate_ranges_and_nonfinite_values_are_rejected():
    assert validate_coordinates(-90, 180) == (-90.0, 180.0)
    for latitude, longitude in ((91, 0), (0, 181), (float("nan"), 0), (0, float("inf")), (True, 0)):
        with pytest.raises(ValueError):
            validate_coordinates(latitude, longitude)


def test_pvlib_spot_check_for_summer_solstice_at_boulder_noon():
    position = calculate_solar(
        39.742,
        -105.178,
        datetime(2024, 6, 21, 19, 0, tzinfo=UTC),
    )
    assert 177 <= position["azimuth_deg"] <= 183
    assert 72 <= position["apparent_elevation_deg"] <= 75


def test_north_south_seasons_and_polar_day_night():
    winter_noon = datetime(2024, 12, 21, 12, 0, tzinfo=UTC)
    northern_winter = calculate_solar(45, 0, winter_noon)
    southern_summer = calculate_solar(-45, 0, winter_noon)
    assert northern_winter["apparent_elevation_deg"] < 30
    assert southern_summer["apparent_elevation_deg"] > 60
    summer_pole = calculate_solar(80, 0, datetime(2024, 6, 21, 12, 0, tzinfo=UTC))
    winter_pole = calculate_solar(80, 0, winter_noon)
    assert summer_pole["apparent_elevation_deg"] > 0
    assert winter_pole["apparent_elevation_deg"] < 0


def test_dawn_daylight_and_night_are_distinct():
    dawn = calculate_solar(0, 0, datetime(2024, 3, 20, 5, 30, tzinfo=UTC))
    daylight = calculate_solar(0, 0, datetime(2024, 3, 20, 7, 0, tzinfo=UTC))
    night = calculate_solar(0, 0, datetime(2024, 3, 20, 18, 30, tzinfo=UTC))
    assert dawn["apparent_elevation_deg"] < 0
    assert daylight["apparent_elevation_deg"] > 0
    assert night["apparent_elevation_deg"] < 0


@pytest.mark.parametrize(("day", "duration", "count"), [
    (date(2024, 3, 10), 23.0, 92),
    (date(2024, 11, 3), 25.0, 100),
])
def test_simulated_local_day_tracks_dst_length(day, duration, count):
    result = sample_local_day(34.05, -118.25, day, "America/Los_Angeles", interval_minutes=15)
    assert result["duration_hours"] == duration
    assert any(sample["apparent_elevation_deg"] > 0 for sample in result["samples"])
    assert all(sample["timestamp"].endswith("Z") for sample in result["samples"])
    assert len(result["samples"]) == count
