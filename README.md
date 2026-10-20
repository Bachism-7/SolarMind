# SolarMind

SolarMind is a local-first solar-tracking preview and guarded ROS 2 command tool for Windows. It has exactly two operating modes: **Live** and **Simulate**. The FastAPI application and browser UI run on the Windows computer at `http://127.0.0.1:8765`. Solar position uses pvlib's NREL Solar Position Algorithm implementation. No weather service, place-search API, or remote web asset is required at runtime.

## Windows setup

Install 64-bit Python 3.12 and Windows OpenSSH Client. Open PowerShell in this project folder, then install the desktop dependencies once while internet access is available:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

Start the application in the foreground:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`. Stop the server with `Ctrl+C`. The app binds to loopback only. It does not expose an unauthenticated API on the LAN.

The PowerShell helpers perform these setup and start steps:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_solar_mind.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start_solar_mind.ps1
```

The server needs no internet after Python packages are installed. Geolocation requires browser permission and a secure context; loopback is a trustworthy origin in current browsers. Coordinates and an IANA timezone can also be entered manually. Set `SOLARMIND_DATA_DIR` in PowerShell before start only if you need a different local settings folder. `.env.example` documents this optional variable; SolarMind reads process environment and does not load `.env` files.

## Use the two modes

**Live** calculates solar position from the saved installation coordinates and the desktop backend clock. The page refreshes its calculation every 15 seconds. Refresh calls are read-only and never contact SSH. Browser geolocation first fills an unsaved candidate; **Confirm as installation site** explicitly replaces the saved coordinates.

**Simulate** calculates a local day from its own selected coordinates, timezone, date, and local time. The timeline, playback, and 1×/60×/360×/1440× speeds are virtual. Simulation has no route to the arm dispatch endpoint. DST gaps return an error. Repeated local times require choosing fold 0 or fold 1. **Copy CLI Commands** only copies manual text; it does not send or run it.

Both views show the raw solar azimuth and apparent elevation, ideal panel target, nominal ID 1 and ID 10 pulses, and their source. Target, last command requested, CLI result, and physical position are separate values. The physical position is always `UNKNOWN` because this app has no servo feedback.

## Dry-run and manual commands

Dry-run is enabled by default. Set a site in **Local settings**, then use **Update Arm Now**. The server calculates a fresh Live target, shows a confirmation dialog, and returns `DRY_RUN` after confirmation. It does not start SSH or publish a ROS message.

In either mode, **Copy CLI Commands** prepares two commands for deliberate manual testing in an already-connected Jetson terminal. Inspect the calibration and movement path first. Paste the ID 1 command, wait for it to finish, then paste ID 10. Copying never means `COMMAND SENT`.

## Existing SSH alias and ROS environment

SolarMind uses the Windows `ssh` executable with `BatchMode=yes`, a five-second connect timeout, and `StrictHostKeyChecking=yes`. Configure an existing alias using the SSH configuration and key/agent that already work for the operator. Example only; replace every placeholder after verifying the host key through a trusted channel:

```sshconfig
Host solarmind-jetson
    HostName <verified-jetson-hostname-or-address>
    User <existing-jetson-user>
    IdentityFile <path-to-existing-private-key>
    IdentitiesOnly yes
    StrictHostKeyChecking yes
```

Enter only the alias in SolarMind. Do not enter a password, private-key contents, arbitrary SSH arguments, or shell commands. If a noninteractive login needs ROS setup, inspect the existing Jetson environment and enter its confirmed absolute setup script path. SolarMind sources that path in the one-shot SSH process only. It does not edit Jetson files or startup profiles.

Use **Refresh connection** only when you deliberately want a read-only remote check. It requests the topic type, topic information, and installed message schema. It does not publish motion. Alternatively, run the included PowerShell check after configuring the alias:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_connection.ps1 -Alias solarmind-jetson
```

This check is read-only. It expects the ROS CLI to be available in the SSH session; use the optional setup path in SolarMind if your verified setup requires it.

## Enabling supervised hardware commissioning later

Physical dispatch remains blocked until all checks pass: dry-run is off, hardware dispatch is explicitly enabled, the SSH alias exists, both axis calibrations are marked verified, a starting pulse estimate exists for both axes, the target is in daylight and within travel limits, and both pulse deltas are within the configured maximum. Azimuth endpoint jumps across the north wrap are always rejected because cable-wrap safety is not known.

When explicitly confirmed, SolarMind creates a new Windows SSH process for servo ID 1, waits for its one-shot CLI result, and starts ID 10 only if ID 1 returned exit code 0 and stdout contains the recognized one-shot output for the requested ID and pulse. The browser request must also remain connected. An unrecognized output or timeout stops the sequence and invalidates that axis's assumed pose. SolarMind does not retry. A failed or unconfirmed second step is reported as `PARTIAL_DISPATCH`; there is no automatic reverse movement. A successful ROS CLI result does not prove physical motion.

Before enabling hardware, complete [the calibration checklist](docs/CALIBRATION_CHECKLIST.md), [the hardware and CLI setup](docs/HARDWARE_AND_CLI_SETUP.md), and [the safety guide](docs/SAFETY_AND_TROUBLESHOOTING.md). Use the physical motor-power cutoff as the independent emergency stop.

## Verification

Run the full local test suite with:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

All publisher tests use injected mock runners. Tests do not open SSH connections, run `ros2 topic pub`, install software on Jetson, or move servos. See [the source notes](docs/SOURCES.md) for official calculation and browser references.
