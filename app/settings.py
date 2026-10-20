"""Validated local settings storage; SSH credentials remain with the user's SSH agent."""

from __future__ import annotations

import copy
import math
import os
import re
import threading
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


DEFAULT_SETTINGS: dict[str, Any] = {
    "installation": {
        "label": "Installation site",
        "latitude": None,
        "longitude": None,
        "timezone": "UTC",
    },
    "ssh": {"alias": "", "ros_setup_path": ""},
    "operation": {
        "dry_run": True,
        "hardware_enabled": False,
        "daylight_threshold_deg": 0.0,
    },
    "calibration": {
        "azimuth_verified": False,
        "azimuth_min_pulse": 0,
        "azimuth_max_pulse": 1000,
        "orientation_note": "",
        "tilt_verified": False,
        "tilt_direction": 1,
        "tilt_offset_deg": 0.0,
        "tilt_min_angle_deg": -90.0,
        "tilt_max_angle_deg": 90.0,
        "tilt_min_pulse": 0,
        "tilt_max_pulse": 1000,
    },
    "safety": {
        "max_delta_pulse": 100,
        "assumed_azimuth_pulse": None,
        "assumed_tilt_pulse": None,
    },
}

_ALIAS = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9_.@-]{0,127})?$")
_REMOTE_PATH = re.compile(r"^/[A-Za-z0-9_./-]{1,240}$")


def default_data_dir() -> Path:
    """Return the platform's per-user SolarMind data directory."""
    override = os.environ.get("SOLARMIND_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "SolarMind"
    return Path.home() / ".solarmind"


def _number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{name} must be finite and within [{low}, {high}]")
    return result


def _integer(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer within [{low}, {high}]")
    return value


def validate_settings(value: Any) -> dict[str, Any]:
    """Validate the complete settings document and return a normalized copy."""
    if not isinstance(value, dict) or set(value) != {"installation", "ssh", "operation", "calibration", "safety"}:
        raise ValueError("Settings must contain installation, ssh, operation, calibration, and safety sections only")
    result = copy.deepcopy(value)
    expected = {
        "installation": {"label", "latitude", "longitude", "timezone"},
        "ssh": {"alias", "ros_setup_path"},
        "operation": {"dry_run", "hardware_enabled", "daylight_threshold_deg"},
        "calibration": {
            "azimuth_verified", "azimuth_min_pulse", "azimuth_max_pulse", "tilt_verified",
            "orientation_note", "tilt_direction", "tilt_offset_deg", "tilt_min_angle_deg", "tilt_max_angle_deg",
            "tilt_min_pulse", "tilt_max_pulse",
        },
        "safety": {"max_delta_pulse", "assumed_azimuth_pulse", "assumed_tilt_pulse"},
    }
    for section, keys in expected.items():
        if not isinstance(result[section], dict) or set(result[section]) != keys:
            raise ValueError(f"{section} settings have missing or unknown fields")

    site = result["installation"]
    if not isinstance(site["label"], str) or len(site["label"].strip()) > 100:
        raise ValueError("installation label must be text no longer than 100 characters")
    if (site["latitude"] is None) != (site["longitude"] is None):
        raise ValueError("latitude and longitude must both be set or both be empty")
    if site["latitude"] is not None:
        site["latitude"] = _number(site["latitude"], "latitude", -90, 90)
        site["longitude"] = _number(site["longitude"], "longitude", -180, 180)
    if not isinstance(site["timezone"], str):
        raise ValueError("timezone must be an IANA timezone name")
    try:
        ZoneInfo(site["timezone"])
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(f"unknown IANA timezone: {site['timezone']}") from error

    ssh = result["ssh"]
    if not isinstance(ssh["alias"], str) or not _ALIAS.fullmatch(ssh["alias"]):
        raise ValueError("SSH alias may contain only letters, numbers, dot, underscore, @, and hyphen")
    if not isinstance(ssh["ros_setup_path"], str):
        raise ValueError("ROS setup path must be text")
    if ssh["ros_setup_path"] and (
        not _REMOTE_PATH.fullmatch(ssh["ros_setup_path"])
        or ".." in ssh["ros_setup_path"].split("/")
    ):
        raise ValueError("ROS setup path must be a simple absolute POSIX path")

    operation = result["operation"]
    for key in ("dry_run", "hardware_enabled"):
        if type(operation[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    operation["daylight_threshold_deg"] = _number(
        operation["daylight_threshold_deg"], "daylight threshold", -6, 20
    )

    calibration = result["calibration"]
    for key in ("azimuth_verified", "tilt_verified"):
        if type(calibration[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    if not isinstance(calibration["orientation_note"], str) or len(calibration["orientation_note"]) > 240:
        raise ValueError("calibration orientation note must be text no longer than 240 characters")
    calibration["tilt_direction"] = _integer(calibration["tilt_direction"], "tilt direction", -1, 1)
    if calibration["tilt_direction"] == 0:
        raise ValueError("tilt direction must be -1 or 1")
    calibration["tilt_offset_deg"] = _number(calibration["tilt_offset_deg"], "tilt offset", -180, 180)
    for axis, lower, upper in (("azimuth", 0, 1000), ("tilt", 0, 1000)):
        low_key, high_key = f"{axis}_min_pulse", f"{axis}_max_pulse"
        calibration[low_key] = _integer(calibration[low_key], low_key, lower, upper)
        calibration[high_key] = _integer(calibration[high_key], high_key, lower, upper)
        if calibration[low_key] >= calibration[high_key]:
            raise ValueError(f"{axis} pulse minimum must be less than its maximum")
    calibration["tilt_min_angle_deg"] = _number(calibration["tilt_min_angle_deg"], "tilt minimum angle", -90, 90)
    calibration["tilt_max_angle_deg"] = _number(calibration["tilt_max_angle_deg"], "tilt maximum angle", -90, 90)
    if calibration["tilt_min_angle_deg"] >= calibration["tilt_max_angle_deg"]:
        raise ValueError("tilt minimum angle must be less than its maximum")

    safety = result["safety"]
    safety["max_delta_pulse"] = _integer(safety["max_delta_pulse"], "maximum pulse delta", 1, 1000)
    for key in ("assumed_azimuth_pulse", "assumed_tilt_pulse"):
        if safety[key] is not None:
            safety[key] = _integer(safety[key], key, 0, 1000)
    return result


class ConfigStore:
    """Atomic YAML configuration store, isolated per local user."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "config.yaml"
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return copy.deepcopy(DEFAULT_SETTINGS)
            with self.path.open("r", encoding="utf-8") as stream:
                parsed = yaml.safe_load(stream)
            return validate_settings(parsed)

    def save(self, value: dict[str, Any]) -> dict[str, Any]:
        normalized = validate_settings(value)
        with self._lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".yaml.tmp")
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                yaml.safe_dump(normalized, stream, sort_keys=False, allow_unicode=True)
            temporary.replace(self.path)
        return normalized
