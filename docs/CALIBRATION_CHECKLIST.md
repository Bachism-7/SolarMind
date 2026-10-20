# Calibration and commissioning checklist

Complete this checklist manually with the arm powered safely and supervised. SolarMind does not contact hardware or move the arm during setup or tests.

## Before enabling dispatch

- [ ] Identify a physical motor-power cutoff and verify it independently. SolarMind does not provide an emergency-stop command.
- [ ] Confirm the correct arm, panel linkage, clear travel path, cable route, and hard stops.
- [ ] Verify the Jetson topic type and message schema using read-only ROS CLI inspection.
- [ ] Verify Windows SSH alias authentication and strict host-key checking.
- [ ] Verify whether the existing noninteractive ROS environment needs an explicit setup path.
- [ ] Keep dry-run enabled while recording the arm's manually observed starting pose.

## Verify ID 1 azimuth mapping

The reported nominal mapping is `round(azimuth_deg / 360 * 1000)`, with logical azimuth clockwise from true north. Verify the physical zero reference and direction at a conservative, supervised range. Record permitted pulse endpoints and cable travel. Pulses 0 and 1000 are distinct mechanical endpoints even though logical bearings 0° and 360° coincide.

SolarMind rejects a target jump between the near-0 and near-1000 pulse regions. It does not infer a safe north crossing or choose a different route.

## Verify ID 10 tilt mapping

The nominal mechanical range is −90° to +90° mapped to pulse 0 to 1000. Panel tilt `beta` is converted using the configured `theta = direction * beta + offset`. Verify linkage direction, offset, mechanical limits, and permitted pulse range physically. Identity mapping is not treated as verified automatically.

## Record and enable

- [ ] Enter verified calibration direction, offset, angle bounds, and pulse bounds in Local settings.
- [ ] Record the verified linkage orientation and physical zero reference in the calibration note.
- [ ] Mark both axes verified only after physical verification.
- [ ] Enter conservative maximum pulse delta.
- [ ] Enter current servo pulses only after establishing the starting pose. These values remain estimates, not feedback.
- [ ] Keep dry-run enabled and review the current calculated target.
- [ ] Confirm daylight target, limits, deltas, cable path, and emergency cutoff.
- [ ] Only then disable dry-run and explicitly enable hardware dispatch.
- [ ] For each supervised update, review the fresh confirmation dialog. Confirm ID 1 completion before the ID 10 step.
- [ ] After any CLI error or partial dispatch, inspect the arm manually. Do not assume its physical position or retry automatically.

Commissioning and physical calibration are operator tasks. They are not performed by this implementation.
