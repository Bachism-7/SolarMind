"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  csrf: "",
  settings: null,
  live: null,
  day: null,
  selectedSample: null,
  currentSimulation: null,
  pendingIntent: null,
  activeMode: "live",
  playTimer: null,
  playEpochMs: 0,
};

function showToast(message, error = false) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.toggle("toast-error", error);
  toast.classList.add("visible");
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => toast.classList.remove("visible"), 3600);
}

function errorMessage(error) {
  const detail = error?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const blockers = detail.dispatch_blockers;
    if (Array.isArray(blockers)) return `${detail.status}: ${blockers.join(", ")}`;
    return detail.status || JSON.stringify(detail);
  }
  return error?.message || "Request failed";
}

async function api(path, options = {}) {
  const method = options.method || "GET";
  const headers = new Headers(options.headers || {});
  if (method !== "GET") {
    headers.set("Content-Type", "application/json");
    headers.set("X-CSRF-Token", state.csrf);
  }
  const response = await fetch(path, {
    ...options,
    method,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw result;
  return result;
}

function setStatusChip(element, status) {
  element.textContent = status.replaceAll("_", " ");
  element.className = "status-chip";
  if (["PREVIEW", "COMMAND_PUBLISHED", "DRY_RUN", "READY_FOR_EXPLICIT_CONFIRMATION"].includes(status)) {
    element.classList.add(status === "COMMAND_PUBLISHED" ? "published-chip" : "ready-chip");
  } else if (["SUN_BELOW_HORIZON", "SITE_NOT_CONFIGURED"].includes(status)) {
    element.classList.add("quiet-chip");
  } else if (["DISPATCH_FAILED", "PARTIAL_DISPATCH", "TARGET_UNREACHABLE"].includes(status)) {
    element.classList.add("error-chip");
  } else {
    element.classList.add("preview-chip");
  }
}

function degrees(value) {
  if (value === null || value === undefined || value === "") return "-";
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)}°` : "-";
}

function pulse(value) {
  return Number.isInteger(value) ? `${value} pulse` : "—";
}

function localClock(value) {
  if (!value) return "—";
  const match = value.match(/T(\d{2}:\d{2}:\d{2})/);
  return match ? match[1] : value;
}

function drawSky(markerId, azimuth, elevation) {
  const marker = $(markerId);
  if (azimuth === null || azimuth === undefined || elevation === null || elevation === undefined
    || !Number.isFinite(Number(azimuth)) || !Number.isFinite(Number(elevation))) {
    marker.setAttribute("visibility", "hidden");
    return;
  }
  const radians = Number(azimuth) * Math.PI / 180;
  const apparent = Number(elevation);
  const radius = apparent > 0
    ? Math.max(0, Math.min(112, (90 - apparent) / 90 * 112))
    : Math.min(128, 112 + Math.abs(apparent));
  const x = 150 + Math.sin(radians) * radius;
  const y = 150 - Math.cos(radians) * radius;
  marker.setAttribute("cx", x.toFixed(2));
  marker.setAttribute("cy", y.toFixed(2));
  marker.setAttribute("visibility", "visible");
  marker.classList.toggle("below-horizon", apparent <= 0);
}

function drawTrack(pathId, samples) {
  const points = samples.filter((item) => item.apparent_elevation_deg > 0).map((item) => {
    const radians = item.azimuth_deg * Math.PI / 180;
    const radius = Math.max(0, Math.min(112, (90 - item.apparent_elevation_deg) / 90 * 112));
    return [150 + Math.sin(radians) * radius, 150 - Math.cos(radians) * radius];
  });
  const path = $(pathId);
  path.setAttribute("d", points.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" "));
}

function fillSettings(settings) {
  state.settings = settings;
  const site = settings.installation;
  const ssh = settings.ssh;
  const operation = settings.operation;
  const calibration = settings.calibration;
  const safety = settings.safety;
  $("setting-label").value = site.label || "";
  $("setting-latitude").value = site.latitude ?? "";
  $("setting-longitude").value = site.longitude ?? "";
  $("setting-timezone").value = site.timezone || "UTC";
  $("setting-ssh-alias").value = ssh.alias || "";
  $("setting-ros-path").value = ssh.ros_setup_path || "";
  $("setting-az-verified").checked = calibration.azimuth_verified;
  $("setting-az-min").value = calibration.azimuth_min_pulse;
  $("setting-az-max").value = calibration.azimuth_max_pulse;
  $("setting-orientation-note").value = calibration.orientation_note || "";
  $("setting-tilt-verified").checked = calibration.tilt_verified;
  $("setting-tilt-direction").value = String(calibration.tilt_direction);
  $("setting-tilt-offset").value = calibration.tilt_offset_deg;
  $("setting-tilt-min-angle").value = calibration.tilt_min_angle_deg;
  $("setting-tilt-max-angle").value = calibration.tilt_max_angle_deg;
  $("setting-tilt-min-pulse").value = calibration.tilt_min_pulse;
  $("setting-tilt-max-pulse").value = calibration.tilt_max_pulse;
  $("setting-max-delta").value = safety.max_delta_pulse;
  $("setting-current-az").value = safety.assumed_azimuth_pulse ?? "";
  $("setting-current-tilt").value = safety.assumed_tilt_pulse ?? "";
  $("setting-daylight").value = operation.daylight_threshold_deg;
  $("setting-hardware-enabled").checked = operation.hardware_enabled;
  $("setting-dry-run").checked = operation.dry_run;
  if (site.latitude !== null) $("sim-latitude").value = site.latitude;
  if (site.longitude !== null) $("sim-longitude").value = site.longitude;
  $("sim-timezone").value = site.timezone || "UTC";
  $("operation-badge").textContent = operation.dry_run ? "DRY RUN" : (operation.hardware_enabled ? "HARDWARE ENABLED" : "HARDWARE DISABLED");
  $("operation-badge").className = `status-chip ${operation.dry_run ? "dry-run-chip" : operation.hardware_enabled ? "error-chip" : "quiet-chip"}`;
}

function readNumeric(id, nullable = false) {
  const raw = $(id).value.trim();
  if (nullable && raw === "") return null;
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error(`${id} must be a finite number`);
  return value;
}

function collectSettings() {
  return {
    installation: {
      label: $("setting-label").value.trim(),
      latitude: readNumeric("setting-latitude", true),
      longitude: readNumeric("setting-longitude", true),
      timezone: $("setting-timezone").value.trim(),
    },
    ssh: {
      alias: $("setting-ssh-alias").value.trim(),
      ros_setup_path: $("setting-ros-path").value.trim(),
    },
    operation: {
      dry_run: $("setting-dry-run").checked,
      hardware_enabled: $("setting-hardware-enabled").checked,
      daylight_threshold_deg: readNumeric("setting-daylight"),
    },
    calibration: {
      azimuth_verified: $("setting-az-verified").checked,
      azimuth_min_pulse: readNumeric("setting-az-min"),
      azimuth_max_pulse: readNumeric("setting-az-max"),
      orientation_note: $("setting-orientation-note").value.trim(),
      tilt_verified: $("setting-tilt-verified").checked,
      tilt_direction: Number($("setting-tilt-direction").value),
      tilt_offset_deg: readNumeric("setting-tilt-offset"),
      tilt_min_angle_deg: readNumeric("setting-tilt-min-angle"),
      tilt_max_angle_deg: readNumeric("setting-tilt-max-angle"),
      tilt_min_pulse: readNumeric("setting-tilt-min-pulse"),
      tilt_max_pulse: readNumeric("setting-tilt-max-pulse"),
    },
    safety: {
      max_delta_pulse: readNumeric("setting-max-delta"),
      assumed_azimuth_pulse: readNumeric("setting-current-az", true),
      assumed_tilt_pulse: readNumeric("setting-current-tilt", true),
    },
  };
}

function renderLastCommand(record) {
  if (!record || record.status === "NO_COMMAND_REQUESTED") {
    $("last-command-status").textContent = "No command requested";
    $("last-command-time").textContent = "Measured physical position: unknown";
    $("last-command-icon").textContent = "—";
    return;
  }
  $("last-command-status").textContent = record.status.replaceAll("_", " ");
  $("last-command-icon").textContent = record.status === "COMMAND_PUBLISHED" ? "✓" : record.status === "DRY_RUN" ? "◌" : "!";
  const stepSummary = Array.isArray(record.steps) && record.steps.length
    ? ` · ${record.steps.map((step) => `ID ${step.servo_id}: ${step.cli_status}`).join(" · ")}`
    : " · CLI not run";
  $("last-command-time").textContent = `${record.requested_at || ""}${stepSummary} · Physical position: unknown`;
}

async function refreshLastCommand() {
  try {
    renderLastCommand(await api("/api/arm/last-command"));
  } catch (error) {
    $("last-command-status").textContent = errorMessage(error);
  }
}

function renderLive(result) {
  state.live = result;
  if (result.status === "SITE_NOT_CONFIGURED") {
    setStatusChip($("live-status"), result.status);
    $("live-action-note").textContent = "Set installation coordinates in Local settings to calculate solar position.";
    $("update-arm").disabled = true;
    $("copy-live").disabled = true;
    $("live-site-label").textContent = "Not configured";
    $("live-coordinates").textContent = "—";
    $("live-local-time").textContent = "--:--:--";
    ["live-sun-azimuth", "live-sun-elevation", "live-panel-azimuth", "live-panel-tilt", "live-servo-1", "live-servo-10"].forEach((id) => $(id).textContent = "—");
    return;
  }
  setStatusChip($("live-status"), result.status);
  $("live-local-time").textContent = localClock(result.local_time);
  $("live-timezone").textContent = `${result.timezone_abbreviation || ""} · ${result.local_time || ""}`;
  $("live-utc-time").textContent = `UTC ${result.utc_time || "—"}`;
  $("live-sun-azimuth").textContent = degrees(result.solar?.azimuth_deg);
  $("live-sun-elevation").textContent = degrees(result.solar?.apparent_elevation_deg);
  $("live-panel-azimuth").textContent = degrees(result.target?.target_azimuth_deg);
  $("live-panel-tilt").textContent = degrees(result.target?.target_tilt_deg);
  const commands = result.servo_commands || [];
  $("live-servo-1").textContent = commands[0] ? pulse(commands[0].position) : "Not available";
  $("live-servo-10").textContent = commands[1] ? pulse(commands[1].position) : "Not available";
  $("calibration-badge").textContent = result.calibration_verified ? "VERIFIED" : "UNVERIFIED";
  $("calibration-badge").className = `status-chip ${result.calibration_verified ? "ready-chip" : "preview-chip"}`;
  $("live-site-label").textContent = result.installation?.label || "Installation site";
  $("live-coordinates").textContent = `${Number(result.latitude).toFixed(4)}, ${Number(result.longitude).toFixed(4)}`;
  drawSky("live-sun-marker", result.solar?.azimuth_deg, result.solar?.apparent_elevation_deg);
  const dryRun = result.dry_run !== false;
  const ready = result.status === "PREVIEW" && (dryRun || result.hardware_ready);
  $("update-arm").disabled = !ready;
  $("copy-live").disabled = !result.manual_commands;
  if (result.status === "SUN_BELOW_HORIZON") {
    $("live-action-note").textContent = "Sun is below the configured daylight threshold. Physical target is unavailable.";
  } else if (!result.calibration_verified && !dryRun) {
    $("live-action-note").textContent = `Dispatch blocked: ${(result.dispatch_blockers || []).join(", ")}.`;
  } else if (dryRun) {
    $("live-action-note").textContent = "Dry run is active. Confirming prepares a preview and never invokes SSH.";
  } else if (result.hardware_ready) {
    $("live-action-note").textContent = "Ready for one explicitly confirmed, sequential one-shot update.";
  } else {
    $("live-action-note").textContent = `Dispatch blocked: ${(result.dispatch_blockers || []).join(", ")}.`;
  }
}

async function refreshLive() {
  if (state.activeMode !== "live") return;
  $("connection-dot").classList.add("checking");
  try {
    const result = await api("/api/live");
    $("connection-dot").classList.remove("checking");
    $("connection-label").textContent = "Local service online";
    renderLive(result);
    await refreshLastCommand();
  } catch (error) {
    $("connection-dot").classList.remove("checking");
    $("connection-dot").classList.add("offline");
    $("connection-label").textContent = "Local service error";
    showToast(errorMessage(error), true);
  }
}

async function saveSettings() {
  const message = $("settings-message");
  message.textContent = "Saving…";
  try {
    const result = await api("/api/settings", { method: "POST", body: JSON.stringify(collectSettings()) });
    fillSettings(result.settings);
    message.textContent = "Saved on this computer.";
    await refreshLive();
  } catch (error) {
    message.textContent = errorMessage(error);
    showToast(errorMessage(error), true);
  }
}

function requestLocation(onSuccess, statusElement) {
  if (!navigator.geolocation) {
    statusElement.textContent = "Browser geolocation is unavailable. Enter coordinates manually.";
    return;
  }
  statusElement.textContent = "Waiting for browser permission…";
  navigator.geolocation.getCurrentPosition(
    (position) => onSuccess(position.coords.latitude, position.coords.longitude, position.coords.accuracy),
    (error) => {
      const reason = error.code === 1 ? "Location permission denied" : error.code === 2 ? "Location unavailable" : "Location request timed out";
      statusElement.textContent = `${reason}. Enter coordinates manually.`;
    },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
  );
}

function useLiveLocation() {
  requestLocation((latitude, longitude, accuracy) => {
    $("setting-latitude").value = latitude.toFixed(6);
    $("setting-longitude").value = longitude.toFixed(6);
    $("live-location-result").textContent = `Candidate: ${latitude.toFixed(5)}, ${longitude.toFixed(5)} ±${Math.round(accuracy)} m. Installation site unchanged.`;
    $("confirm-location-live").hidden = false;
  }, $("live-location-result"));
}

async function confirmLiveLocation() {
  if (!window.confirm("Save this browser location as the solar installation site? This will replace the currently saved installation coordinates.")) return;
  await saveSettings();
  $("confirm-location-live").hidden = true;
}

function useSimulationLocation() {
  requestLocation((latitude, longitude, accuracy) => {
    $("sim-latitude").value = latitude.toFixed(6);
    $("sim-longitude").value = longitude.toFixed(6);
    $("sim-time-message").textContent = `Browser location ±${Math.round(accuracy)} m. Simulation only; saved installation unchanged.`;
  }, $("sim-time-message"));
}

async function prepareArm() {
  const button = $("update-arm");
  button.disabled = true;
  try {
    const intent = await api("/api/arm/prepare", { method: "POST", body: "{}" });
    state.pendingIntent = intent;
    $("confirm-operator").checked = false;
    $("confirm-send").disabled = true;
    $("confirm-title").textContent = intent.status === "DRY_RUN_PREPARED" ? "Confirm dry-run preview" : "Review the requested movement";
    $("confirm-send").textContent = intent.status === "DRY_RUN_PREPARED" ? "Confirm dry run" : "Send one-shot sequence";
    const commands = intent.servo_commands || [];
    $("dialog-target").textContent = `Panel ${degrees(intent.target.target_azimuth_deg)} azimuth · ${degrees(intent.target.target_tilt_deg)} tilt. ID 1: ${pulse(commands[0]?.position)}; ID 10: ${pulse(commands[1]?.position)}.`;
    $("dialog-warning").textContent = intent.status === "DRY_RUN_PREPARED"
      ? "Dry run is active. No SSH process or ROS publisher will run. This preview uses nominal, potentially unverified calibration."
      : "This sends two one-shot CLI commands through a new Windows SSH process. Confirm calibration, cable travel, physical clearance, and motor-power cutoff first.";
    $("confirm-dialog").showModal();
  } catch (error) {
    showToast(errorMessage(error), true);
  } finally {
    button.disabled = !state.live || state.live.status !== "PREVIEW" ||
      (!state.live.dry_run && !state.live.hardware_ready);
  }
}

async function confirmOneShot() {
  const intent = state.pendingIntent;
  if (!intent) return;
  $("confirm-send").disabled = true;
  $("confirm-send").textContent = "Working…";
  try {
    const result = await api("/api/arm/one-shot", {
      method: "POST",
      body: JSON.stringify({ intent_token: intent.token, confirmed: true }),
    });
    state.pendingIntent = null;
    $("confirm-dialog").close();
    for (const step of result.steps || []) {
      if (step.cli_status !== "CLI_RETURNED_SUCCESS" || !state.settings) continue;
      if (step.servo_id === 1) {
        state.settings.safety.assumed_azimuth_pulse = step.position;
        $("setting-current-az").value = step.position;
      } else if (step.servo_id === 10) {
        state.settings.safety.assumed_tilt_pulse = step.position;
        $("setting-current-tilt").value = step.position;
      }
    }
    renderLastCommand(result);
    const message = result.status === "DRY_RUN"
      ? "Dry run complete. No command was sent."
      : result.status === "COMMAND_PUBLISHED"
        ? "CLI returned success for both commands. Physical position remains unknown."
        : `${result.status.replaceAll("_", " ")}. Check step results; no automatic retry occurred.`;
    showToast(message, result.status === "PARTIAL_DISPATCH" || result.status === "DISPATCH_FAILED");
    await refreshLive();
  } catch (error) {
    showToast(errorMessage(error), true);
  } finally {
    $("confirm-send").textContent = state.pendingIntent?.status === "DRY_RUN_PREPARED" ? "Confirm dry run" : "Send one-shot sequence";
    $("confirm-send").disabled = true;
  }
}

async function refreshConnection() {
  const button = $("refresh-connection");
  button.disabled = true;
  button.textContent = "Checking…";
  $("connection-detail").textContent = "Running explicit read-only ROS topic diagnostics over SSH…";
  try {
    const result = await api("/api/connection/check", { method: "POST", body: "{}" });
    $("connection-detail").textContent = result.output || result.status.replaceAll("_", " ");
    $("connection-label").textContent = result.status === "CONNECTION_CHECKED" ? "Jetson CLI reachable" : result.status.replaceAll("_", " ");
    $("connection-dot").classList.toggle("offline", result.status !== "CONNECTION_CHECKED");
  } catch (error) {
    $("connection-detail").textContent = errorMessage(error);
    $("connection-dot").classList.add("offline");
  } finally {
    button.disabled = false;
    button.textContent = "Refresh connection";
  }
}

function nearestSampleIndex(samples, epochSeconds) {
  let bestIndex = 0;
  let bestDistance = Infinity;
  samples.forEach((sample, index) => {
    const distance = Math.abs(sample.epoch_seconds - epochSeconds);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestIndex;
}

function selectedSimulationTime() {
  const date = $("sim-date").value;
  const time = $("sim-time").value;
  if (!date || !time) throw new Error("Choose a local date and time before loading the virtual day.");
  const payload = {
    latitude: readNumeric("sim-latitude"),
    longitude: readNumeric("sim-longitude"),
    timezone: $("sim-timezone").value.trim(),
    local_datetime: `${date}T${time}:00`,
  };
  if ($("sim-fold").value !== "") payload.fold = Number($("sim-fold").value);
  return { date, time, payload };
}

function renderSimulation(result, sourceSample = null) {
  state.currentSimulation = result;
  const source = sourceSample || result;
  $("sim-selected-time").textContent = `${source.local_timestamp || result.local_time || ""} · ${source.timestamp || result.utc_time || ""}`;
  $("sim-sun-azimuth").textContent = degrees(source.azimuth_deg ?? result.solar?.azimuth_deg);
  $("sim-sun-elevation").textContent = degrees(source.apparent_elevation_deg ?? result.solar?.apparent_elevation_deg);
  const target = source.target_azimuth_deg !== undefined
    ? { target_azimuth_deg: source.target_azimuth_deg, target_tilt_deg: source.target_tilt_deg, status: source.status }
    : result.target;
  $("sim-panel-azimuth").textContent = degrees(target?.target_azimuth_deg);
  $("sim-panel-tilt").textContent = degrees(target?.target_tilt_deg);
  const commands = source.servo_commands || result.servo_commands || [];
  $("sim-servo-1").textContent = commands[0] ? pulse(commands[0].position) : "Not available";
  $("sim-servo-10").textContent = commands[1] ? pulse(commands[1].position) : "Not available";
  drawSky("sim-sun-marker", source.azimuth_deg ?? result.solar?.azimuth_deg, source.apparent_elevation_deg ?? result.solar?.apparent_elevation_deg);
  $("copy-sim").disabled = !source.manual_commands && !result.manual_commands;
  $("copy-sim").dataset.commands = source.manual_commands || result.manual_commands || "";
  const localLabel = source.local_time || source.local_timestamp || result.local_time || "";
  $("sim-timeline-label").textContent = localLabel.length > 5 ? localLabel.slice(11, 16) : localLabel || "-";
}

async function loadDay() {
  stopPlayback();
  const button = $("load-day");
  button.disabled = true;
  button.textContent = "Calculating…";
  try {
    const selectedTime = selectedSimulationTime();
    const validatedTime = await api("/api/solar", {
      method: "POST",
      body: JSON.stringify(selectedTime.payload),
    });
    const day = await api("/api/simulate/day", {
      method: "POST",
      body: JSON.stringify({
        latitude: selectedTime.payload.latitude,
        longitude: selectedTime.payload.longitude,
        timezone: selectedTime.payload.timezone,
        date: selectedTime.date,
        interval_minutes: 15,
      }),
    });
    state.day = day;
    drawTrack("sim-track", day.samples);
    $("sim-day-label").textContent = `${day.date} · ${day.timezone}`;
    $("sim-duration").textContent = `${day.duration_hours} hour local day · ${day.samples.length} samples`;
    $("sim-timeline").min = "0";
    $("sim-timeline").max = String(day.samples.length - 1);
    $("sim-timeline").disabled = false;
    document.querySelectorAll("[data-sim-step], #sim-play").forEach((button) => button.disabled = false);
    const matching = day.samples.map((sample, index) => ({ sample, index }))
      .filter(({ sample }) => sample.local_time === selectedTime.time && sample.fold === validatedTime.fold);
    const index = matching.length
      ? matching[0].index
      : nearestSampleIndex(day.samples, Date.parse(validatedTime.utc_time) / 1000);
    selectSample(index);
    $("sim-time-message").textContent = "Virtual day loaded. Playback changes only simulated time.";
  } catch (error) {
    $("sim-time-message").textContent = errorMessage(error);
    showToast(errorMessage(error), true);
  } finally {
    button.disabled = false;
    button.textContent = "Load virtual day";
  }
}

function setSimulationInputs(sample) {
  const local = sample.local_timestamp || "";
  if (local.length >= 16) {
    $("sim-date").value = local.slice(0, 10);
    $("sim-time").value = local.slice(11, 16);
    $("sim-fold").value = String(sample.fold ?? 0);
  }
}

function selectSample(index) {
  if (!state.day?.samples?.length) return;
  const selected = Math.max(0, Math.min(state.day.samples.length - 1, Number(index)));
  const sample = state.day.samples[selected];
  state.selectedSample = selected;
  $("sim-timeline").value = String(selected);
  setSimulationInputs(sample);
  renderSimulation(sample, sample);
}

async function calculateSelectedTime() {
  try {
    const { payload } = selectedSimulationTime();
    const result = await api("/api/solar", { method: "POST", body: JSON.stringify(payload) });
    renderSimulation(result);
    $("sim-time-message").textContent = "Solar position calculated for the selected local time.";
  } catch (error) {
    $("sim-time-message").textContent = errorMessage(error);
    showToast(errorMessage(error), true);
  }
}

function stopPlayback() {
  if (state.playTimer !== null) window.clearInterval(state.playTimer);
  state.playTimer = null;
  $("sim-play").textContent = "Play";
}

function togglePlayback() {
  if (state.playTimer !== null) {
    stopPlayback();
    return;
  }
  if (!state.day?.samples?.length) return;
  const selected = state.day.samples[state.selectedSample || 0];
  const selectedTimestamp = state.currentSimulation?.utc_time || state.currentSimulation?.timestamp;
  state.playEpochMs = Date.parse(selectedTimestamp) || selected.epoch_seconds * 1000;
  $("sim-play").textContent = "Pause";
  state.playTimer = window.setInterval(() => {
    const speed = Number($("sim-speed").value);
    state.playEpochMs += 1000 * speed;
    const first = state.day.samples[0].epoch_seconds * 1000;
    const last = state.day.samples[state.day.samples.length - 1].epoch_seconds * 1000;
    if (state.playEpochMs > last) state.playEpochMs = first;
    const index = nearestSampleIndex(state.day.samples, state.playEpochMs / 1000);
    if (index !== state.selectedSample) selectSample(index);
  }, 1000);
}

async function stepTimeline(stepMinutes) {
  if (!state.day?.samples?.length || !state.currentSimulation) return;
  stopPlayback();
  const currentTimestamp = state.currentSimulation.utc_time || state.currentSimulation.timestamp;
  const currentEpochMs = Date.parse(currentTimestamp);
  if (!Number.isFinite(currentEpochMs)) return;
  const firstEpochMs = state.day.samples[0].epoch_seconds * 1000;
  const lastEpochMs = state.day.samples[state.day.samples.length - 1].epoch_seconds * 1000;
  const nextEpochMs = Math.max(firstEpochMs, Math.min(lastEpochMs, currentEpochMs + stepMinutes * 60_000));
  if (nextEpochMs === currentEpochMs) return;
  try {
    const result = await api("/api/solar", {
      method: "POST",
      body: JSON.stringify({
        latitude: readNumeric("sim-latitude"),
        longitude: readNumeric("sim-longitude"),
        timezone: $("sim-timezone").value.trim(),
        timestamp: new Date(nextEpochMs).toISOString(),
      }),
    });
    state.selectedSample = nearestSampleIndex(state.day.samples, nextEpochMs / 1000);
    $("sim-timeline").value = String(state.selectedSample);
    $("sim-date").value = result.local_time.slice(0, 10);
    $("sim-time").value = result.local_time.slice(11, 16);
    $("sim-fold").value = String(result.fold ?? 0);
    renderSimulation(result);
    $("sim-time-message").textContent = `Virtual time moved ${stepMinutes > 0 ? "+" : ""}${stepMinutes} minutes. Hardware is not contacted.`;
  } catch (error) {
    $("sim-time-message").textContent = errorMessage(error);
    showToast(errorMessage(error), true);
  }
}

async function copyCommands(value) {
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    showToast("Commands copied. Copy does not send or run them.");
  } catch {
    const textArea = document.createElement("textarea");
    textArea.value = value;
    textArea.setAttribute("readonly", "");
    textArea.className = "clipboard-buffer";
    document.body.append(textArea);
    textArea.select();
    const copied = document.execCommand("copy");
    textArea.remove();
    showToast(copied ? "Commands copied. Copy does not send or run them." : "Clipboard access failed. Select the command text manually.", !copied);
  }
}

function switchMode(mode) {
  state.activeMode = mode;
  document.querySelectorAll(".mode-tab").forEach((button) => {
    const active = button.dataset.mode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  $("live-view").hidden = mode !== "live";
  $("live-view").classList.toggle("active", mode === "live");
  $("simulate-view").hidden = mode !== "simulate";
  $("simulate-view").classList.toggle("active", mode === "simulate");
  if (mode === "live") refreshLive();
}

async function start() {
  try {
    const bootstrap = await api("/api/bootstrap");
    state.csrf = bootstrap.csrf_token;
    fillSettings(bootstrap.settings);
    await refreshLive();
    const dateInSiteZone = state.live?.local_time?.slice(0, 10);
    $("sim-date").value = dateInSiteZone || new Date().toISOString().slice(0, 10);
  } catch (error) {
    $("connection-label").textContent = "Local service unavailable";
    $("connection-dot").classList.add("offline");
    showToast(errorMessage(error), true);
  }
}

document.querySelectorAll(".mode-tab").forEach((button) => button.addEventListener("click", () => switchMode(button.dataset.mode)));
$("refresh-live").addEventListener("click", refreshLive);
$("save-settings").addEventListener("click", saveSettings);
$("use-location-live").addEventListener("click", useLiveLocation);
$("confirm-location-live").addEventListener("click", confirmLiveLocation);
$("use-location-sim").addEventListener("click", useSimulationLocation);
$("update-arm").addEventListener("click", prepareArm);
$("confirm-operator").addEventListener("change", () => $("confirm-send").disabled = !$("confirm-operator").checked);
$("confirm-send").addEventListener("click", confirmOneShot);
$("cancel-confirm").addEventListener("click", () => $("confirm-dialog").close());
$("confirm-dialog").addEventListener("close", () => { state.pendingIntent = null; $("confirm-operator").checked = false; });
$("refresh-connection").addEventListener("click", refreshConnection);
$("copy-live").addEventListener("click", () => copyCommands(state.live?.manual_commands));
$("load-day").addEventListener("click", loadDay);
$("calculate-time").addEventListener("click", calculateSelectedTime);
$("sim-timeline").addEventListener("input", (event) => { stopPlayback(); selectSample(event.target.value); });
$("sim-play").addEventListener("click", togglePlayback);
document.querySelectorAll("[data-sim-step]").forEach((button) => {
  button.addEventListener("click", () => stepTimeline(Number(button.dataset.simStep)));
});
$("copy-sim").addEventListener("click", () => copyCommands($("copy-sim").dataset.commands));
window.setInterval(() => { if (state.activeMode === "live") refreshLive(); }, 15000);
start();
