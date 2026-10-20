"""pvlib-based solar position and virtual-day sampling."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from typing import Any, Iterable

import pandas as pd
import pvlib

from .timezone_utils import first_valid_local_midnight, get_zone


def validate_coordinates(latitude: Any, longitude: Any) -> tuple[float, float]:
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        raise ValueError("Coordinates must be finite numbers")
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError) as error:
        raise ValueError("Coordinates must be finite numbers") from error
    if not math.isfinite(lat) or not -90 <= lat <= 90:
        raise ValueError("Latitude must be finite and within [-90, 90]")
    if not math.isfinite(lon) or not -180 <= lon <= 180:
        raise ValueError("Longitude must be finite and within [-180, 180]")
    return lat, lon


def calculate_solar_many(
    latitude: Any, longitude: Any, timestamps: Iterable[datetime]
) -> list[dict[str, float]]:
    lat, lon = validate_coordinates(latitude, longitude)
    values = list(timestamps)
    if not values:
        return []
    if any(value.tzinfo is None or value.utcoffset() is None for value in values):
        raise ValueError("Every solar timestamp must include timezone information")
    index = pd.DatetimeIndex([pd.Timestamp(value) for value in values])
    positions = pvlib.solarposition.get_solarposition(index, lat, lon, method="nrel_numpy")
    result: list[dict[str, float]] = []
    for row in positions.itertuples():
        azimuth = float(row.azimuth) % 360.0
        elevation = float(row.apparent_elevation)
        if not math.isfinite(azimuth) or not math.isfinite(elevation):
            raise ValueError("Solar calculation returned a non-finite angle")
        result.append({"azimuth_deg": azimuth, "apparent_elevation_deg": elevation})
    return result


def calculate_solar(latitude: Any, longitude: Any, timestamp: datetime) -> dict[str, float]:
    return calculate_solar_many(latitude, longitude, [timestamp])[0]


def panel_target(solar: dict[str, float], daylight_threshold_deg: float = 0.0) -> dict[str, Any]:
    elevation = solar["apparent_elevation_deg"]
    if elevation <= daylight_threshold_deg:
        return {
            "status": "SUN_BELOW_HORIZON",
            "sun_above_horizon": elevation > 0.0,
            "target_azimuth_deg": None,
            "target_tilt_deg": None,
        }
    tilt = 90.0 - elevation
    if not 0.0 <= tilt <= 90.0:
        return {
            "status": "TARGET_UNREACHABLE",
            "sun_above_horizon": True,
            "target_azimuth_deg": None,
            "target_tilt_deg": None,
        }
    return {
        "status": "PREVIEW",
        "sun_above_horizon": True,
        "target_azimuth_deg": solar["azimuth_deg"] % 360.0,
        "target_tilt_deg": tilt,
    }


def sample_local_day(
    latitude: Any,
    longitude: Any,
    day: date,
    timezone_name: str,
    daylight_threshold_deg: float = 0.0,
    interval_minutes: int = 15,
) -> dict[str, Any]:
    if not 1 <= interval_minutes <= 60:
        raise ValueError("Sample interval must be between 1 and 60 minutes")
    start = first_valid_local_midnight(day, timezone_name)
    next_day = day + timedelta(days=1)
    end = first_valid_local_midnight(next_day, timezone_name)
    start_utc = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)
    instants: list[datetime] = []
    cursor = start_utc
    while cursor < end_utc:
        instants.append(cursor)
        cursor += timedelta(minutes=interval_minutes)
    solar_values = calculate_solar_many(latitude, longitude, instants)
    zone = get_zone(timezone_name)
    samples = []
    for instant, solar in zip(instants, solar_values, strict=True):
        local = instant.astimezone(zone)
        target = panel_target(solar, daylight_threshold_deg)
        samples.append(
            {
                "timestamp": instant.isoformat().replace("+00:00", "Z"),
                "epoch_seconds": instant.timestamp(),
                "local_timestamp": local.isoformat(),
                "local_time": local.strftime("%H:%M"),
                "fold": local.fold,
                **solar,
                **target,
            }
        )
    return {
        "date": day.isoformat(),
        "timezone": timezone_name,
        "interval_minutes": interval_minutes,
        "duration_hours": (end_utc - start_utc).total_seconds() / 3600.0,
        "samples": samples,
    }
