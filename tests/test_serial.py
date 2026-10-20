from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import serial_link
from app.main import create_app

CFG = serial_link.load_config()


class FakeSerial:
    """Pretends to be a Jetson console: asks for login, then echoes commands and answers them."""

    def __init__(self, *args, **kwargs):
        self.out = b""
        self.stage = "login"
        self.sent = []

    def reset_input_buffer(self):
        self.out = b""

    def write(self, data):
        text = data.decode().strip()
        self.sent.append(text)
        if self.stage == "login":
            if text == "":
                self.out += b"\r\nhost login: " if not self.out else b""
            elif text == "bob":
                self.out += b"Password: "
                self.stage = "password"
        elif self.stage == "password":
            self.stage = "shell"
            self.out += b"\r\nuser@host:~$ "
        else:
            self.out += f"{text}\r\n".encode()
            if "topic pub" in text:
                self.out += b"publisher: beginning loop\r\npublishing #1: x\r\n"
            self.out += b"user@host:~$ "

    def read(self, size):
        data, self.out = self.out[:size], self.out[size:]
        return data

    def close(self):
        pass


def test_login_then_commands_run_in_order():
    cfg = SimpleNamespace(**{**vars(CFG), "USERNAME": "bob", "PASSWORD": "pw", "LOGIN_TIMEOUT": 5, "COMMAND_TIMEOUT": 2})
    fake = FakeSerial()
    with serial_link.SerialSession("COM7", cfg, opener=lambda *a, **k: fake) as link:
        link.login()
        output = link.run(serial_link.pulse_command(1, 250))
    assert "bob" in fake.sent and "pw" in fake.sent
    assert "publishing #1" in output


def test_bad_port_and_pulse_are_rejected():
    with pytest.raises(ValueError):
        serial_link.SerialSession("COM7; rm -rf /", CFG, opener=FakeSerial)
    with pytest.raises(ValueError):
        serial_link.pulse_command(1, 5000)


def test_servo_pulses_use_calibration():
    pulses = serial_link.servo_pulses(90.0, 45.0, CFG)
    assert pulses == [{"id": 1, "position": 250}, {"id": 10, "position": 750}]


def test_send_endpoint_previews_without_opening_a_port():
    client = TestClient(create_app(), base_url="http://127.0.0.1:8765")
    body = {"latitude": 39.742, "longitude": -105.178, "timestamp": "2024-06-21T19:00:00Z"}
    result = client.post("/api/send", json=body).json()
    assert result["sent"] is False and len(result["cli_commands"]) == 2
    night = client.post("/api/send", json={**body, "timestamp": "2024-06-21T07:00:00Z"})
    assert night.status_code == 422
    forged = client.post("/api/send", json={**body, "send": True}, headers={"origin": "http://evil.example"})
    assert forged.status_code == 403
