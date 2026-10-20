# Safety and troubleshooting

## Safety boundaries

- Only the Live confirmation flow can reach `/api/arm/one-shot`. Simulate has no dispatch call in its UI or API flow.
- Live refresh, settings reads, solar calculations, and day sampling do not publish motion.
- Dry-run defaults to enabled; hardware dispatch defaults to disabled.
- A physical sequence requires verified calibrations, a configured SSH alias, an assumed starting pulse for both axes, configured pulse and angle limits, a daylight target, and bounded pulse deltas.
- Unknown starting pose is rejected. The last requested pulse is only an estimate. This app has no measured servo feedback.
- Azimuth wrap jumps between pulse endpoints are rejected. No automatic parking, retries, rollback, or periodic movement exists.
- SSH uses a fresh process, `BatchMode=yes`, `ConnectTimeout=5`, and `StrictHostKeyChecking=yes`. The remote publisher is always `ros2 topic pub --once`.
- A publish step counts as CLI-confirmed only when the exit code is zero and ROS output reports the requested one-shot message. An unrecognized output format fails closed.
- A timeout or unconfirmed output invalidates that axis's assumed pulse estimate. New hardware preparation remains blocked until the operator establishes and records the current pose.
- A successful CLI exit means only that the CLI returned success. It does not prove the servo moved or reached target.

## Common failures

**Site is not configured.** Enter latitude, longitude, and an IANA timezone in Local settings. Browser geolocation fills an unsaved candidate and does not replace the saved installation without explicit confirmation.

**`SUN_BELOW_HORIZON`.** The target is not enabled below the configured daylight threshold. Solar azimuth and apparent elevation remain available for display.

**DST ambiguous local time.** Select the first occurrence (`fold 0`) or second occurrence (`fold 1`). The API requires an explicit choice.

**DST nonexistent local time.** Choose a valid local time. The application rejects the gap rather than silently shifting it.

**`CALIBRATION_NOT_VERIFIED` or `STARTING_POSE_UNKNOWN`.** Complete the supervised calibration checklist and enter the observed starting pulses. Do not mark an unverified identity profile as safe.

**Pulse travel or maximum delta blocked.** Check the verified mechanical range and current pose manually. Increase limits only after reviewing arm clearance and travel. North-wrap jumps remain blocked.

**SSH connection check fails.** Confirm the existing alias, host key, key agent, batch authentication, and read-only ROS environment. SolarMind does not install SSH credentials or modify Jetson startup files.

**First CLI command fails or its output is unrecognized.** ID 10 is not started. Inspect the returned exit code and SSH/ROS setup. Manually establish the current pose and update its assumed pulse estimate before preparing another command.

**Second CLI command fails or its output is unrecognized.** Status is `PARTIAL_DISPATCH`; ID 1 was confirmed and ID 10 was not. The ID 10 assumed pose is invalidated. Inspect the arm manually and establish its pose before any further command. SolarMind does not reverse or retry.

**CLI success but arm did not move.** The CLI result is not position feedback. Inspect power, servo wiring, ROS subscriber state, mechanics, and physical position manually. Use the independent motor-power cutoff when needed.
