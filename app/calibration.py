"""Nominal servo mapping and explicit panel-to-mechanical tilt calibration."""

from __future__ import annotations

import math
from typing import Any


def azimuth_to_pulse(azimuth_deg: float) -> int:
    """Map the closed mechanical endpoint range; logical targets stay below 360°."""
    if not math.isfinite(azimuth_deg) or not 0 <= azimuth_deg <= 360:
        raise ValueError("Azimuth endpoint must be in [0, 360]")
    return round(azimuth_deg / 360.0 * 1000.0)


def map_targets(
    azimuth_deg: float, panel_tilt_deg: float, calibration: dict[str, Any]
) -> dict[str, Any]:
    if not math.isfinite(azimuth_deg) or not 0 <= azimuth_deg < 360:
        raise ValueError("Panel azimuth must be in [0, 360)")
    if not math.isfinite(panel_tilt_deg) or not 0 <= panel_tilt_deg <= 90:
        raise ValueError("Panel tilt must be in [0, 90]")
    mechanical_tilt = calibration["tilt_direction"] * panel_tilt_deg + calibration["tilt_offset_deg"]
    if not -90 <= mechanical_tilt <= 90:
        raise ValueError("Calibrated mechanical tilt is outside [-90, 90]")
    if not calibration["tilt_min_angle_deg"] <= mechanical_tilt <= calibration["tilt_max_angle_deg"]:
        raise ValueError("Calibrated mechanical tilt is outside configured travel limits")
    azimuth_pulse = azimuth_to_pulse(azimuth_deg)
    tilt_pulse = round((mechanical_tilt + 90.0) / 180.0 * 1000.0)
    if not 0 <= azimuth_pulse <= 1000 or not 0 <= tilt_pulse <= 1000:
        raise ValueError("Nominal servo pulse is outside [0, 1000]")
    if not calibration["azimuth_min_pulse"] <= azimuth_pulse <= calibration["azimuth_max_pulse"]:
        raise ValueError("Azimuth pulse is outside configured travel limits")
    if not calibration["tilt_min_pulse"] <= tilt_pulse <= calibration["tilt_max_pulse"]:
        raise ValueError("Tilt pulse is outside configured travel limits")
    return {
        "servo_commands": [
            {"id": 1, "position": azimuth_pulse},
            {"id": 10, "position": tilt_pulse},
        ],
        "mechanical_tilt_deg": mechanical_tilt,
        "calibration_verified": bool(calibration["azimuth_verified"] and calibration["tilt_verified"]),
    }
