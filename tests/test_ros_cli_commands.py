import pytest

from app.ros_cli_commands import (
    build_manual_commands,
    build_read_only_diagnostics,
    build_remote_command,
    build_topic_pub_command,
)


def test_exact_once_message_and_servo_order():
    first = build_topic_pub_command(1, 583)
    second = build_topic_pub_command(10, 806)
    assert first == "ros2 topic pub --once /ros_robot_controller/bus_servo/set_position ros_robot_controller_msgs/msg/ServosPosition '{\"position\":[{\"id\":1,\"position\":583}]}'"
    assert second == "ros2 topic pub --once /ros_robot_controller/bus_servo/set_position ros_robot_controller_msgs/msg/ServosPosition '{\"position\":[{\"id\":10,\"position\":806}]}'"
    assert "duration" not in first + second
    manual = build_manual_commands(583, 806)
    assert manual.index('"id":1') < manual.index('"id":10')
    assert manual.count("--once") == 2


@pytest.mark.parametrize(("servo_id", "pulse"), [(2, 100), (1, -1), (10, 1001), (True, 1), (1, 1.5)])
def test_invalid_id_or_pulse_is_rejected(servo_id, pulse):
    with pytest.raises(ValueError):
        build_topic_pub_command(servo_id, pulse)


def test_remote_setup_path_is_quoted_and_diagnostics_are_read_only():
    command = build_remote_command(1, 500, "/opt/ros/humble/setup.bash")
    assert command.startswith("bash -lc ")
    assert "ros2 topic pub --once" in command
    diagnostic = build_read_only_diagnostics("/opt/ros/humble/setup.bash")
    assert "ros2 topic type" in diagnostic and "ros2 topic info" in diagnostic
    assert "ros2 interface show ros_robot_controller_msgs/msg/ServosPosition" in diagnostic
    assert "topic pub" not in diagnostic

