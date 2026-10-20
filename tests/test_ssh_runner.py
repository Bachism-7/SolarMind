from unittest.mock import Mock, patch

from app.ssh_runner import SSHCommandRunner


def test_runner_uses_argument_vector_strict_host_key_and_bounded_timeout():
    completed = Mock(returncode=0, stdout="ok", stderr="")
    with patch("app.ssh_runner.subprocess.run", return_value=completed) as run:
        result = SSHCommandRunner(executable="ssh-test", timeout_seconds=7).run("jetson", "ros2 topic type /topic")
    assert result.exit_code == 0
    args, kwargs = run.call_args
    assert args[0][0] == "ssh-test"
    assert "BatchMode=yes" in args[0]
    assert "StrictHostKeyChecking=yes" in args[0]
    assert args[0][-2:] == ["jetson", "ros2 topic type /topic"]
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 7


def test_runner_turns_timeout_into_bounded_failure():
    import subprocess

    with patch("app.ssh_runner.subprocess.run", side_effect=subprocess.TimeoutExpired("ssh", 15)):
        result = SSHCommandRunner().run("jetson", "ros2 topic type /topic")
    assert result.exit_code == 124
    assert result.timed_out is True
