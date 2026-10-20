"use strict";

const $ = (id) => document.getElementById(id);
const state = { samples: [], current: null };

function say(text, error = false) {
  $("message").textContent = text;
  $("message").classList.toggle("error", error);
}

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Request failed");
  return result;
}

function place() {
  const latitude = $("latitude").value.trim();
  const longitude = $("longitude").value.trim();
  if (latitude === "" || longitude === "") throw new Error("Enter latitude and longitude.");
  return { latitude: Number(latitude), longitude: Number(longitude) };
}

function skyPoint(azimuth, elevation) {
  const radius = elevation > 0 ? (90 - elevation) / 90 * 112 : Math.min(128, 112 - elevation);
  const radians = azimuth * Math.PI / 180;
  return [150 + Math.sin(radians) * radius, 150 - Math.cos(radians) * radius];
}

function show(azimuth, elevation, utcIso) {
  state.current = utcIso;
  $("time").textContent = `${utcIso.slice(11, 16)} UTC`;
  $("azimuth").textContent = `${azimuth.toFixed(1)}°`;
  $("elevation").textContent = `${elevation.toFixed(1)}°`;
  $("tilt").textContent = elevation > 0 ? `${(90 - elevation).toFixed(1)}°` : "sun below horizon";
  $("daylight").textContent = elevation > 0 ? "above horizon" : "below horizon";
  const [x, y] = skyPoint(azimuth, elevation);
  const sun = $("sun");
  sun.setAttribute("cx", x.toFixed(1));
  sun.setAttribute("cy", y.toFixed(1));
  sun.setAttribute("visibility", "visible");
  sun.classList.toggle("below", elevation <= 0);
}

function select(index) {
  const sample = state.samples[index];
  if (!sample) return;
  $("timeline").value = String(index);
  $("date").value = sample.timestamp.slice(0, 10);
  $("time-input").value = sample.timestamp.slice(11, 16);
  show(sample.azimuth_deg, sample.apparent_elevation_deg, sample.timestamp);
}

function nearest(epochSeconds) {
  let best = 0;
  state.samples.forEach((sample, index) => {
    if (Math.abs(sample.epoch_seconds - epochSeconds) < Math.abs(state.samples[best].epoch_seconds - epochSeconds)) best = index;
  });
  return best;
}

async function calculate() {
  try {
    const utcDate = $("date").value;
    const utcTime = $("time-input").value;
    if (!utcDate || !utcTime) throw new Error("Enter a UTC date and time.");
    const timestamp = `${utcDate}T${utcTime}:00Z`;
    const current = await post("/api/solar", { ...place(), timestamp });
    const day = await post("/api/day", { ...place(), date: utcDate });
    state.samples = day.samples;
    const path = day.samples.filter((s) => s.apparent_elevation_deg > 0).map((s, i) => {
      const [x, y] = skyPoint(s.azimuth_deg, s.apparent_elevation_deg);
      return `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
    });
    $("track").setAttribute("d", path.join(" "));
    $("timeline").max = String(day.samples.length - 1);
    $("timeline").value = String(nearest(Date.parse(timestamp) / 1000));
    $("timeline").disabled = false;
    show(current.azimuth_deg, current.apparent_elevation_deg, current.utc_time);
    say("");
  } catch (error) {
    say(error.message, true);
  }
}

function now() {
  const iso = new Date().toISOString();
  $("date").value = iso.slice(0, 10);
  $("time-input").value = iso.slice(11, 16);
  calculate();
}

async function armRequest(send) {
  const output = $("arm-output");
  if (!state.current) { output.textContent = "Calculate a sun position first."; return; }
  output.textContent = send ? "Connecting over serial (this can take up to a minute)..." : "";
  try {
    const result = await post("/api/send", { ...place(), timestamp: state.current, send, port: $("port").value.trim() });
    const lines = result.cli_commands.map((c, i) => `ID ${result.servo_commands[i].id} -> pulse ${result.servo_commands[i].position}\n  ${c}`);
    if (result.steps) {
      result.steps.forEach((s) => lines.push(`ID ${s.servo_id}: ${s.published ? "published" : "NOT CONFIRMED"}`));
      lines.push(result.all_published ? "Both commands published. This is not proof the arm moved." : "Stopped: a command was not confirmed.");
    }
    output.textContent = lines.join("\n");
  } catch (error) {
    output.textContent = error.message;
  }
}

async function loadSerial() {
  try {
    const info = await (await fetch("/api/serial")).json();
    $("port").value = info.port;
    $("ports").innerHTML = "";
    info.ports.forEach((name) => $("ports").append(new Option(name)));
    if (!info.login_configured) $("arm-output").textContent = "serial_login.py not found - copy serial_login.example.py to serial_login.py and set your login.";
  } catch { /* the page still works without serial */ }
}

$("date").value = new Date().toISOString().slice(0, 10);
["latitude", "longitude", "date", "time-input"].forEach((id) => {
  $(id).addEventListener("change", () => { if ($("latitude").value !== "" && $("longitude").value !== "") calculate(); });
});
$("calculate").addEventListener("click", calculate);
$("now").addEventListener("click", now);
$("timeline").addEventListener("input", (event) => select(Number(event.target.value)));
$("preview").addEventListener("click", () => armRequest(false));
$("send").addEventListener("click", () => armRequest(true));
$("confirm").addEventListener("change", (event) => { $("send").disabled = !event.target.checked; });
loadSerial();
