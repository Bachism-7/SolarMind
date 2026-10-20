import copy
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.calibration import map_targets
from app.main import create_app
from app.ros_cli_commands import build_remote_command
from app.settings import DEFAULT_SETTINGS
from app.solar import calculate_solar, panel_target
from app.ssh_runner import RunnerResult


class RecordingRunner:
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = []

    def run(self, alias, remote_command):
        self.calls.append((alias, remote_command))
        return self.results.pop(0) if self.results else RunnerResult(0)


def publication_output(servo_id, pulse):
    return (
        "publisher: beginning loop\n"
        f"publishing #1: ServosPosition(position=[ServoPosition(id={servo_id}, position={pulse})])\n"
    )


NOW = datetime(2024, 6, 21, 18, 0, tzinfo=UTC)


def make_client(tmp_path, runner=None):
    client = TestClient(
        create_app(tmp_path, runner=runner or RecordingRunner(), clock=lambda: NOW),
        base_url="http://127.0.0.1:8765",
    )
    bootstrap = client.get("/api/bootstrap").json()
    headers = {
        "Origin": "http://127.0.0.1:8765",
        "X-CSRF-Token": bootstrap["csrf_token"],
    }
    return client, headers


def physical_settings():
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings["installation"].update(
        label="Test site", latitude=39.742, longitude=-105.178, timezone="America/Denver"
    )
    settings["ssh"]["alias"] = "solarmind-jetson"
    settings["operation"].update(dry_run=False, hardware_enabled=True)
    settings["calibration"].update(azimuth_verified=True, tilt_verified=True)
    solar = calculate_solar(39.742, -105.178, NOW)
    target = panel_target(solar)
    commands = map_targets(
        target["target_azimuth_deg"], target["target_tilt_deg"], settings["calibration"]
    )["servo_commands"]
    settings["safety"].update(
        assumed_azimuth_pulse=commands[0]["position"],
        assumed_tilt_pulse=commands[1]["position"],
        max_delta_pulse=100,
    )
    return settings, commands


def prepare_physical(client, headers):
    settings, expected_commands = physical_settings()
    saved = client.post("/api/settings", json=settings, headers=headers)
    assert saved.status_code == 200
    response = client.post("/api/arm/prepare", json={}, headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "READY_FOR_EXPLICIT_CONFIRMATION"
    assert result["servo_commands"] == expected_commands
    return result


def test_dry_run_confirmation_never_calls_ssh(tmp_path):
    runner = RecordingRunner()
    client, headers = make_client(tmp_path, runner)
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings["installation"].update(latitude=39.742, longitude=-105.178, timezone="America/Denver")
    assert client.post("/api/settings", json=settings, headers=headers).status_code == 200
    prepared = client.post("/api/arm/prepare", json={}, headers=headers)
    assert prepared.status_code == 200
    intent = prepared.json()
    response = client.post(
        "/api/arm/one-shot",
        json={"intent_token": intent["token"], "confirmed": True},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "DRY_RUN"
    assert response.json()["motion_confirmed"] is False
    assert response.json()["actual_position"] == "UNKNOWN"
    assert runner.calls == []


def test_id1_then_id10_run_sequentially_after_explicit_confirmation(tmp_path):
    runner = RecordingRunner()
    client, headers = make_client(tmp_path, runner)
    prepared = prepare_physical(client, headers)
    commands = prepared["servo_commands"]
    runner.results.extend(
        [
            RunnerResult(0, publication_output(1, commands[0]["position"])),
            RunnerResult(0, publication_output(10, commands[1]["position"])),
        ]
    )
    response = client.post(
        "/api/arm/one-shot",
        json={"intent_token": prepared["token"], "confirmed": True},
        headers=headers,
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "COMMAND_PUBLISHED"
    assert result["cli_status"] == "CLI_RETURNED_SUCCESS"
    assert result["motion_confirmed"] is False
    assert result["actual_position"] == "UNKNOWN"
    assert runner.calls == [
        ("solarmind-jetson", build_remote_command(1, commands[0]["position"])),
        ("solarmind-jetson", build_remote_command(10, commands[1]["position"])),
    ]
    assert [step["servo_id"] for step in result["steps"]] == [1, 10]


def test_failed_first_step_stops_before_id10(tmp_path):
    runner = RecordingRunner([RunnerResult(1, stderr="mock failure")])
    client, headers = make_client(tmp_path, runner)
    prepared = prepare_physical(client, headers)
    response = client.post(
        "/api/arm/one-shot",
        json={"intent_token": prepared["token"], "confirmed": True},
        headers=headers,
    )
    assert response.json()["status"] == "DISPATCH_FAILED"
    assert len(runner.calls) == 1
    assert response.json()["steps"][0]["servo_id"] == 1


def test_failed_second_step_reports_partial_dispatch_without_retry(tmp_path):
    runner = RecordingRunner()
    client, headers = make_client(tmp_path, runner)
    prepared = prepare_physical(client, headers)
    commands = prepared["servo_commands"]
    runner.results.extend(
        [
            RunnerResult(0, publication_output(1, commands[0]["position"])),
            RunnerResult(1, stderr="mock failure"),
        ]
    )
    response = client.post(
        "/api/arm/one-shot",
        json={"intent_token": prepared["token"], "confirmed": True},
        headers=headers,
    )
    result = response.json()
    assert result["status"] == "PARTIAL_DISPATCH"
    assert [step["servo_id"] for step in result["steps"]] == [1, 10]
    assert len(runner.calls) == 2


def test_overlapping_one_shot_is_rejected_without_consuming_intent(tmp_path):
    runner = RecordingRunner()
    client, headers = make_client(tmp_path, runner)
    prepared = prepare_physical(client, headers)
    commands = prepared["servo_commands"]
    runner.results.extend(
        [
            RunnerResult(0, publication_output(1, commands[0]["position"])),
            RunnerResult(0, publication_output(10, commands[1]["position"])),
        ]
    )
    lock = client.app.state.runtime.dispatch_lock
    assert lock.acquire(blocking=False)
    try:
        overlapping = client.post(
            "/api/arm/one-shot",
            json={"intent_token": prepared["token"], "confirmed": True},
            headers=headers,
        )
        assert overlapping.status_code == 409
        assert runner.calls == []
    finally:
        lock.release()
    accepted = client.post(
        "/api/arm/one-shot",
        json={"intent_token": prepared["token"], "confirmed": True},
        headers=headers,
    )
    assert accepted.status_code == 200
    assert runner.calls == [
        ("solarmind-jetson", build_remote_command(1, commands[0]["position"])),
        ("solarmind-jetson", build_remote_command(10, commands[1]["position"])),
    ]


def test_missing_confirmation_and_reused_token_are_rejected(tmp_path):
    client, headers = make_client(tmp_path)
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings["installation"].update(latitude=39.742, longitude=-105.178, timezone="America/Denver")
    client.post("/api/settings", json=settings, headers=headers)
    intent = client.post("/api/arm/prepare", json={}, headers=headers).json()
    missing = client.post(
        "/api/arm/one-shot",
        json={"intent_token": intent["token"], "confirmed": False},
        headers=headers,
    )
    assert missing.status_code == 400
    accepted = client.post(
        "/api/arm/one-shot",
        json={"intent_token": intent["token"], "confirmed": True},
        headers=headers,
    )
    assert accepted.status_code == 200
    replayed = client.post(
        "/api/arm/one-shot",
        json={"intent_token": intent["token"], "confirmed": True},
        headers=headers,
    )
    assert replayed.status_code == 409


def test_settings_change_invalidates_prepared_one_shot(tmp_path):
    runner = RecordingRunner()
    client, headers = make_client(tmp_path, runner)
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings["installation"].update(latitude=39.742, longitude=-105.178, timezone="America/Denver")
    client.post("/api/settings", json=settings, headers=headers)
    intent = client.post("/api/arm/prepare", json={}, headers=headers).json()
    changed = copy.deepcopy(settings)
    changed["installation"]["label"] = "Changed after preparation"
    assert client.post("/api/settings", json=changed, headers=headers).status_code == 200
    response = client.post(
        "/api/arm/one-shot",
        json={"intent_token": intent["token"], "confirmed": True},
        headers=headers,
    )
    assert response.status_code == 409
    assert runner.calls == []


def test_read_endpoints_and_simulation_do_not_call_command_runner(tmp_path):
    runner = RecordingRunner()
    client, headers = make_client(tmp_path, runner)
    assert client.get("/").status_code == 200
    assert client.get("/api/health").json()["loopback_only"] is True
    assert client.get("/api/live").json()["status"] == "SITE_NOT_CONFIGURED"
    assert client.get("/api/arm/last-command").json()["actual_position"] == "UNKNOWN"
    solar = client.post(
        "/api/solar",
        json={
            "latitude": 39.742,
            "longitude": -105.178,
            "timezone": "America/Denver",
            "local_datetime": "2024-06-21T12:00:00",
        },
        headers=headers,
    )
    assert solar.status_code == 200
    assert solar.json()["dispatch_allowed"] is False
    assert solar.json()["hardware_ready"] is False
    assert solar.json()["local_time"].startswith("2024-06-21T12:00:00-06:00")
    day = client.post(
        "/api/simulate/day",
        json={
            "latitude": 39.742,
            "longitude": -105.178,
            "timezone": "America/Denver",
            "date": "2024-06-21",
            "interval_minutes": 60,
        },
        headers=headers,
    )
    assert day.status_code == 200
    assert day.json()["samples"][12]["manual_commands"].count("--once") == 2
    assert runner.calls == []


@pytest.mark.parametrize("output_case", ["unrelated", "extra_line"])
def test_unexpected_zero_exit_output_stops_before_id10_and_invalidates_pose(tmp_path, output_case):
    runner = RecordingRunner()
    client, headers = make_client(tmp_path, runner)
    prepared = prepare_physical(client, headers)
    if output_case == "unrelated":
        output = "operation completed"
    else:
        command = prepared["servo_commands"][0]
        output = publication_output(1, command["position"]) + "unexpected diagnostic\n"
    runner.results.append(RunnerResult(0, output))
    response = client.post(
        "/api/arm/one-shot",
        json={"intent_token": prepared["token"], "confirmed": True},
        headers=headers,
    )
    result = response.json()
    assert result["status"] == "DISPATCH_FAILED"
    assert result["cli_status"] == "FAILED"
    assert result["steps"][0]["cli_status"] == "CLI_OUTPUT_UNRECOGNIZED"
    assert result["steps"][0]["publication_confirmed"] is False
    assert len(runner.calls) == 1
    safety = client.get("/api/bootstrap").json()["settings"]["safety"]
    assert safety["assumed_azimuth_pulse"] is None
    assert safety["assumed_tilt_pulse"] == prepared["servo_commands"][1]["position"]
    blocked = client.post("/api/arm/prepare", json={}, headers=headers)
    assert blocked.status_code == 409
    assert "STARTING_POSE_UNKNOWN" in blocked.json()["detail"]["dispatch_blockers"]


def test_timeout_invalidates_affected_assumed_pose_and_blocks_reprepare(tmp_path):
    runner = RecordingRunner(
        [RunnerResult(124, "publisher: beginning loop", "SSH command timed out", timed_out=True)]
    )
    client, headers = make_client(tmp_path, runner)
    prepared = prepare_physical(client, headers)
    response = client.post(
        "/api/arm/one-shot",
        json={"intent_token": prepared["token"], "confirmed": True},
        headers=headers,
    )
    assert response.json()["status"] == "DISPATCH_FAILED"
    assert response.json()["steps"][0]["timed_out"] is True
    assert len(runner.calls) == 1
    safety = client.get("/api/bootstrap").json()["settings"]["safety"]
    assert safety["assumed_azimuth_pulse"] is None
    assert safety["assumed_tilt_pulse"] == prepared["servo_commands"][1]["position"]
    blocked = client.post("/api/arm/prepare", json={}, headers=headers)
    assert blocked.status_code == 409
    assert "STARTING_POSE_UNKNOWN" in blocked.json()["detail"]["dispatch_blockers"]


def test_configured_pulse_bounds_block_preview_and_simulation_commands(tmp_path):
    client, headers = make_client(tmp_path)
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings["calibration"]["azimuth_max_pulse"] = 100
    assert client.post("/api/settings", json=settings, headers=headers).status_code == 200

    preview = client.post(
        "/api/preview",
        json={
            "mode": "simulate",
            "latitude": 39.742,
            "longitude": -105.178,
            "timezone": "America/Denver",
            "timestamp": NOW.isoformat(),
        },
        headers=headers,
    )
    assert preview.status_code == 200
    assert preview.json()["status"] == "TARGET_UNREACHABLE"
    assert preview.json()["servo_commands"] is None
    assert preview.json()["manual_commands"] is None

    day = client.post(
        "/api/simulate/day",
        json={
            "latitude": 39.742,
            "longitude": -105.178,
            "timezone": "America/Denver",
            "date": "2024-06-21",
            "interval_minutes": 60,
        },
        headers=headers,
    )
    assert day.status_code == 200
    unreachable = [sample for sample in day.json()["samples"] if sample["status"] == "TARGET_UNREACHABLE"]
    assert unreachable
    assert all(sample["servo_commands"] is None for sample in unreachable)
    assert all(sample["manual_commands"] is None for sample in unreachable)


def test_explicit_connection_check_is_read_only(tmp_path):
    runner = RecordingRunner([RunnerResult(0, "ros_robot_controller_msgs/msg/ServosPosition")])
    client, headers = make_client(tmp_path, runner)
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings["ssh"]["alias"] = "solarmind-jetson"
    assert client.post("/api/settings", json=settings, headers=headers).status_code == 200
    response = client.post("/api/connection/check", json={}, headers=headers)
    assert response.status_code == 200
    assert response.json()["read_only"] is True
    assert len(runner.calls) == 1
    remote = runner.calls[0][1]
    assert "ros2 topic type" in remote and "ros2 topic info" in remote
    assert "ros2 interface show ros_robot_controller_msgs/msg/ServosPosition" in remote
    assert "topic pub" not in remote


def test_cross_origin_post_is_rejected(tmp_path):
    client, headers = make_client(tmp_path)
    headers["Origin"] = "http://attacker.example"
    response = client.post("/api/settings", json=DEFAULT_SETTINGS, headers=headers)
    assert response.status_code == 403
