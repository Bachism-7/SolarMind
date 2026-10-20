"""Pre-dispatch checks for calibration, travel bounds, pose estimates, and step size."""

from __future__ import annotations

from typing import Any


def dispatch_blockers(settings: dict[str, Any], commands: list[dict[str, int]]) -> list[str]:
    blockers: list[str] = []
    operation = settings["operation"]
    calibration = settings["calibration"]
    safety = settings["safety"]
    if operation["dry_run"]:
        blockers.append("DRY_RUN_ENABLED")
    if not operation["hardware_enabled"]:
        blockers.append("HARDWARE_DISPATCH_DISABLED")
    if not settings["ssh"]["alias"]:
        blockers.append("SSH_ALIAS_NOT_CONFIGURED")
    if not calibration["azimuth_verified"] or not calibration["tilt_verified"]:
        blockers.append("CALIBRATION_NOT_VERIFIED")
    if safety["assumed_azimuth_pulse"] is None or safety["assumed_tilt_pulse"] is None:
        blockers.append("STARTING_POSE_UNKNOWN")
        return blockers
    targets = {item["id"]: item["position"] for item in commands}
    limits = {
        1: (calibration["azimuth_min_pulse"], calibration["azimuth_max_pulse"], safety["assumed_azimuth_pulse"]),
        10: (calibration["tilt_min_pulse"], calibration["tilt_max_pulse"], safety["assumed_tilt_pulse"]),
    }
    for servo_id in (1, 10):
        lower, upper, current = limits[servo_id]
        target = targets[servo_id]
        if not lower <= target <= upper:
            blockers.append(f"SERVO_{servo_id}_TRAVEL_LIMIT")
        if abs(target - current) > safety["max_delta_pulse"]:
            blockers.append(f"SERVO_{servo_id}_MAX_DELTA_EXCEEDED")
        if servo_id == 1 and (
            (current >= 900 and target <= 100) or (current <= 100 and target >= 900)
        ):
            blockers.append("AZIMUTH_WRAP_UNVERIFIED")
    return blockers
