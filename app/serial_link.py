"""Serial-port session to the robot: log in, then run fixed ROS 2 servo commands."""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import serial
from serial.tools import list_ports

TOPIC = "/ros_robot_controller/bus_servo/set_position"
MESSAGE_TYPE = "ros_robot_controller_msgs/msg/ServosPosition"
PORT_NAME = re.compile(r"^(COM\d{1,3}|/dev/tty[A-Za-z0-9_.-]{1,30})$")
CONFIG_DIR = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "PORT": "COM7", "BAUDRATE": 115200, "USERNAME": "", "PASSWORD": "",
    "LOGIN_PROMPT": r"login:\s*$", "PASSWORD_PROMPT": r"[Pp]assword:\s*$", "SHELL_PROMPT": r"[$#]\s*$",
    "ROS_SETUP": "", "LOGIN_TIMEOUT": 20, "COMMAND_TIMEOUT": 25,
    "AZIMUTH_SERVO_ID": 1, "TILT_SERVO_ID": 10,
    "AZIMUTH_MIN_PULSE": 0, "AZIMUTH_MAX_PULSE": 1000, "TILT_MIN_PULSE": 0, "TILT_MAX_PULSE": 1000,
    "TILT_DIRECTION": 1, "TILT_OFFSET_DEG": 0.0,
}


class SerialError(RuntimeError):
    pass


def load_config(directory: Path = CONFIG_DIR) -> SimpleNamespace:
    """Read serial_login.py (falling back to the example) fresh, so edits apply at once."""
    path = directory / "serial_login.py"
    configured = path.exists()
    if not configured:
        path = directory / "serial_login.example.py"
    values = dict(DEFAULTS)
    if path.exists():
        spec = importlib.util.spec_from_file_location("solarmind_serial_login", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        values.update({k: getattr(module, k) for k in DEFAULTS if hasattr(module, k)})
    values["configured"] = configured
    return SimpleNamespace(**values)


def available_ports() -> list[str]:
    return [port.device for port in list_ports.comports()]


def pulse_command(servo_id: int, pulse: int) -> str:
    """One fixed ROS 2 publish command; only validated integers are interpolated."""
    if type(servo_id) is not int or type(pulse) is not int or not 0 <= pulse <= 1000:
        raise ValueError("Servo id and pulse (0-1000) must be integers")
    message = json.dumps({"position": [{"id": servo_id, "position": pulse}]}, separators=(",", ":"))
    return f"ros2 topic pub --once {TOPIC} {MESSAGE_TYPE} {shlex.quote(message)}"


def servo_pulses(azimuth_deg: float, tilt_deg: float, cfg: SimpleNamespace) -> list[dict[str, int]]:
    """Map panel azimuth (0-360) and tilt (0-90) to servo pulses using the config limits."""
    mechanical = cfg.TILT_DIRECTION * tilt_deg + cfg.TILT_OFFSET_DEG
    if not -90 <= mechanical <= 90:
        raise ValueError("Calibrated tilt is outside -90..90 degrees")
    az_pulse = round(azimuth_deg % 360.0 / 360.0 * 1000.0)
    tilt_pulse = round((mechanical + 90.0) / 180.0 * 1000.0)
    if not cfg.AZIMUTH_MIN_PULSE <= az_pulse <= cfg.AZIMUTH_MAX_PULSE:
        raise ValueError(f"Azimuth pulse {az_pulse} is outside the configured limits")
    if not cfg.TILT_MIN_PULSE <= tilt_pulse <= cfg.TILT_MAX_PULSE:
        raise ValueError(f"Tilt pulse {tilt_pulse} is outside the configured limits")
    return [{"id": cfg.AZIMUTH_SERVO_ID, "position": az_pulse}, {"id": cfg.TILT_SERVO_ID, "position": tilt_pulse}]


class SerialSession:
    """Open a port, get to a shell prompt (logging in if needed), run commands in order."""

    def __init__(self, port: str, cfg: SimpleNamespace, opener: Callable[..., Any] = serial.Serial):
        if not PORT_NAME.match(port):
            raise ValueError("Port must look like COM7 (or /dev/ttyUSB0)")
        self.cfg = cfg
        try:
            self.conn = opener(port, cfg.BAUDRATE, timeout=0.2, write_timeout=5)
        except (serial.SerialException, OSError) as error:
            raise SerialError(f"Could not open {port} (is PuTTY or another program using it?): {error}") from error

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "SerialSession":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _read_until(self, patterns: list[str], timeout: float) -> tuple[int, str]:
        """Read until the tail of the output matches one pattern; returns (index, text) or (-1, text)."""
        compiled = [re.compile(p) for p in patterns]
        buffer = ""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            chunk = self.conn.read(4096)
            if chunk:
                buffer += chunk.decode("utf-8", "replace").replace("\r", "")
                tail = buffer.rstrip(" ").split("\n")[-1] if not buffer.endswith("\n") else ""
                for index, pattern in enumerate(compiled):
                    if pattern.search(tail):
                        return index, buffer
        return -1, buffer

    def _send(self, text: str) -> None:
        self.conn.write(text.encode("utf-8") + b"\n")

    def login(self) -> None:
        cfg = self.cfg
        self.conn.reset_input_buffer()
        self._send("")
        deadline = time.monotonic() + cfg.LOGIN_TIMEOUT
        while time.monotonic() < deadline:
            index, _ = self._read_until([cfg.SHELL_PROMPT, cfg.LOGIN_PROMPT, cfg.PASSWORD_PROMPT], 3)
            if index == 0:
                break
            if index == 1:
                self._send(cfg.USERNAME)
            elif index == 2:
                self._send(cfg.PASSWORD)
            else:
                self._send("")
        else:
            raise SerialError("Timed out waiting for a shell prompt after login")
        if cfg.ROS_SETUP:
            self.run(cfg.ROS_SETUP)

    def run(self, command: str) -> str:
        self._send(command)
        index, output = self._read_until([self.cfg.SHELL_PROMPT], self.cfg.COMMAND_TIMEOUT)
        if index != 0:
            raise SerialError("Timed out waiting for the command to finish")
        return output
