# SolarMind

SolarMind is a small local web page that shows where the sun is. It uses pvlib's NREL Solar Position Algorithm, runs on your own computer at `http://127.0.0.1:8765`, and needs no internet access or API keys once installed.

## Setup (Windows)

Requires Python 3.11 or newer.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

## Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`. Stop the server with `Ctrl+C`.

## Use

Enter latitude, longitude, a UTC date and a UTC time. The azimuth, elevation and panel tilt update as you edit. **Now (UTC)** fills in the current time. The slider scrubs through the chosen UTC day and the sky chart shows the sun's path (centre is straight overhead, edge is the horizon, north is up).

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Driving the arm over a serial port

SolarMind can send the shown sun position to the robot directly over a COM port using pyserial, so PuTTY is not needed. Only one program can hold a COM port at a time, so close PuTTY before pressing **Send to arm**.

1. Copy `serial_login.example.py` to `serial_login.py` (it is git-ignored) and edit it: `PORT`, `BAUDRATE`, `USERNAME`, `PASSWORD`, optional `ROS_SETUP`, the servo ids, pulse limits and tilt calibration. It is re-read on every request, so no restart is needed.
2. In the page, check the COM port (it can be changed there), press **Preview commands** to see exactly what would be sent, tick the confirmation box, then press **Send to arm**.

SolarMind opens the port, logs in if the device shows a login prompt, optionally runs `ROS_SETUP`, then publishes servo 1 (azimuth) followed by servo 10 (tilt) with `ros2 topic pub --once`. It stops if the first command is not confirmed. A published command does not prove the arm moved, and the default calibration is unverified: check it on the real hardware first.
