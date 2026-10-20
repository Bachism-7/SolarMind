import copy

import pytest

from app.calibration import azimuth_to_pulse, map_targets
from app.safety import dispatch_blockers
from app.settings import DEFAULT_SETTINGS, validate_settings


def test_nominal_servo_mapping_and_example():
    profile = DEFAULT_SETTINGS["calibration"]
    zero = map_targets(0, 0, profile)
    example = map_targets(210, 55, profile)
    assert [item["position"] for item in zero["servo_commands"]] == [0, 500]
    assert [item["position"] for item in example["servo_commands"]] == [583, 806]
    assert map_targets(180, 0, profile)["servo_commands"][0]["position"] == 500
    assert [azimuth_to_pulse(value) for value in (0, 180, 360)] == [0, 500, 1000]


def test_identity_calibration_is_reported_unverified_by_default():
    mapped = map_targets(90, 45, DEFAULT_SETTINGS["calibration"])
    assert mapped["calibration_verified"] is False
    assert mapped["mechanical_tilt_deg"] == 45


def test_configured_pulse_limits_reject_unreachable_targets():
    profile = copy.deepcopy(DEFAULT_SETTINGS["calibration"])
    profile["azimuth_max_pulse"] = 100
    with pytest.raises(ValueError, match="Azimuth pulse is outside configured travel limits"):
        map_targets(90, 45, profile)

    profile = copy.deepcopy(DEFAULT_SETTINGS["calibration"])
    profile["tilt_min_pulse"] = 600
    with pytest.raises(ValueError, match="Tilt pulse is outside configured travel limits"):
        map_targets(90, 0, profile)


def ready_settings():
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings["operation"].update(dry_run=False, hardware_enabled=True)
    settings["ssh"]["alias"] = "solarmind-jetson"
    settings["calibration"].update(azimuth_verified=True, tilt_verified=True)
    settings["safety"].update(assumed_azimuth_pulse=500, assumed_tilt_pulse=750, max_delta_pulse=100)
    return validate_settings(settings)


def test_unknown_pose_and_unverified_calibration_block_motion():
    settings = ready_settings()
    settings["safety"]["assumed_azimuth_pulse"] = None
    blockers = dispatch_blockers(settings, [{"id": 1, "position": 500}, {"id": 10, "position": 750}])
    assert "STARTING_POSE_UNKNOWN" in blockers
    settings = ready_settings()
    settings["calibration"]["tilt_verified"] = False
    assert "CALIBRATION_NOT_VERIFIED" in dispatch_blockers(settings, [{"id": 1, "position": 500}, {"id": 10, "position": 750}])


def test_travel_delta_and_azimuth_wrap_are_rejected():
    settings = ready_settings()
    blockers = dispatch_blockers(settings, [{"id": 1, "position": 900}, {"id": 10, "position": 750}])
    assert "SERVO_1_MAX_DELTA_EXCEEDED" in blockers
    settings["safety"]["max_delta_pulse"] = 1000
    settings["safety"]["assumed_azimuth_pulse"] = 990
    blockers = dispatch_blockers(settings, [{"id": 1, "position": 10}, {"id": 10, "position": 750}])
    assert "AZIMUTH_WRAP_UNVERIFIED" in blockers


def test_pulse_outside_configured_travel_is_blocked():
    settings = ready_settings()
    settings["calibration"]["azimuth_max_pulse"] = 700
    blockers = dispatch_blockers(settings, [{"id": 1, "position": 800}, {"id": 10, "position": 750}])
    assert "SERVO_1_TRAVEL_LIMIT" in blockers


def test_invalid_tilt_profile_is_rejected():
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings["calibration"]["tilt_direction"] = 0
    with pytest.raises(ValueError, match="-1 or 1"):
        validate_settings(settings)
