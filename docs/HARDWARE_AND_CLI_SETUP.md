# Hardware and CLI setup

SolarMind runs on the operator's Windows computer. It reuses the existing Jetson ROS 2 installation over a fresh SSH process. No files, services, dependencies, launch files, shell-profile changes, or persistent publisher nodes are installed on Jetson.

## Configure Windows OpenSSH

1. Confirm an existing SSH alias works from PowerShell with batch authentication and strict host-key checking.
2. Configure the alias using the operator's already-provisioned key or SSH agent. Verify the Jetson host key through a trusted channel. Do not disable host-key checking.
3. Enter the alias in SolarMind's **Existing Jetson SSH connection** field. SolarMind never accepts a password or private-key text.
4. Use **Refresh connection** to run read-only `ros2 topic type`, `ros2 topic info`, and `ros2 interface show` checks. These checks run only after an explicit click.
5. If noninteractive SSH does not load ROS, inspect the existing installation and enter its confirmed setup script path. SolarMind uses `bash -lc` and sources that path for that SSH process only. It never guesses a ROS distribution or workspace path.

Do not use `StrictHostKeyChecking=no`. Do not put free-form commands or SSH options in the alias or setup-path fields.

## Existing ROS message and command

The configured topic and type are fixed:

```text
/ros_robot_controller/bus_servo/set_position
ros_robot_controller_msgs/msg/ServosPosition
```

The gateway generates one `ros2 topic pub --once` process per servo. It sends ID 1 first and starts ID 10 only after ID 1 returns zero and its output contains the recognized one-shot publication for the requested servo ID and pulse. The recognized output requires `publisher: beginning loop` followed by exactly one `publishing #1:` record whose message text contains the expected `id` and `position` fields. Unknown output formats fail closed. Each process has a 15-second timeout. A timeout, nonzero exit, unrecognized output, missing CLI, lost SSH session, or failed first step stops the sequence. There are no automatic retries.

Generated manual commands use this form:

```bash
ros2 topic pub --once /ros_robot_controller/bus_servo/set_position ros_robot_controller_msgs/msg/ServosPosition '{"position":[{"id":1,"position":583}]}'
```

Pulse numbers above are illustrative only. Do not run them on hardware without operator-verified calibration and clearance. No `duration` field or alternate topic is used.

## Status meanings

- `PREVIEW`: calculated target and nominal pulse mapping.
- `MANUAL COMMANDS PREPARED`: copyable text exists; no command was sent.
- `DRY_RUN`: the operator confirmed a preview while dry-run remained enabled; no SSH publish ran.
- `COMMAND_PUBLISHED`: both one-shot CLI processes returned zero and their output matched each requested servo ID and pulse. Physical position remains `UNKNOWN`.
- `PARTIAL_DISPATCH`: ID 1 was confirmed and ID 10 failed, timed out, returned unrecognized output, or the browser disconnected between steps. SolarMind stops and does not reverse or retry.
- `DISPATCH_FAILED`: ID 1 failed, timed out, or returned unrecognized output; ID 10 was not started.

An unconfirmed or timed-out step invalidates that axis's assumed pulse estimate. A new hardware preparation stays blocked until the operator establishes and records the current pose. The audit record stores timestamp, request ID, requested pulses, per-step exit result, and status. It does not store SSH keys, passwords, raw commands, or ROS output as a durable log.
