"""Pure builders for fixed one-shot and read-only ROS 2 CLI commands."""

from __future__ import annotations

import json
import shlex


TOPIC = "/ros_robot_controller/bus_servo/set_position"
MESSAGE_TYPE = "ros_robot_controller_msgs/msg/ServosPosition"
ALLOWED_PULSES = range(0, 1001)


def _validate(servo_id: int, pulse: int) -> None:
    if type(servo_id) is not int or servo_id not in (1, 10):
        raise ValueError("Servo ID must be 1 or 10")
    if type(pulse) is not int or pulse not in ALLOWED_PULSES:
        raise ValueError("Servo pulse must be an integer within [0, 1000]")


def build_topic_pub_command(servo_id: int, pulse: int) -> str:
    """Build one POSIX shell command with fixed tokens and a validated integer."""
    _validate(servo_id, pulse)
    message = json.dumps(
        {"position": [{"id": servo_id, "position": pulse}]},
        separators=(",", ":"),
    )
    return (
        f"ros2 topic pub --once {TOPIC} {MESSAGE_TYPE} "
        f"{shlex.quote(message)}"
    )


def build_remote_command(servo_id: int, pulse: int, ros_setup_path: str = "") -> str:
    command = build_topic_pub_command(servo_id, pulse)
    if not ros_setup_path:
        return command
    shell_script = f"source {shlex.quote(ros_setup_path)} && exec {command}"
    return f"bash -lc {shlex.quote(shell_script)}"


def build_manual_commands(azimuth_pulse: int, tilt_pulse: int) -> str:
    """Build exact, deliberately copyable commands in the required servo order."""
    first = build_topic_pub_command(1, azimuth_pulse)
    second = build_topic_pub_command(10, tilt_pulse)
    return (
        "# Manual/external testing only. Review calibration and clearance first.\n"
        f"# Step 1: azimuth servo ID 1\n{first}\n"
        "# Step 2: tilt servo ID 10, only after step 1 completes safely\n"
        f"{second}"
    )


def build_read_only_diagnostics(ros_setup_path: str = "") -> str:
    """Build fixed connection diagnostics; this command cannot publish motion."""
    command = (
        f"ros2 topic type {TOPIC} && "
        f"ros2 topic info {TOPIC} && "
        f"ros2 interface show {MESSAGE_TYPE}"
    )
    if not ros_setup_path:
        return command
    shell_script = f"source {shlex.quote(ros_setup_path)} && {command}"
    return f"bash -lc {shlex.quote(shell_script)}"
