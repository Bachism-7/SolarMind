"""Loopback-only FastAPI site and guarded desktop SSH gateway."""

from __future__ import annotations

import asyncio
import hmac
import re
import secrets
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .calibration import map_targets
from .ros_cli_commands import (
    build_manual_commands,
    build_read_only_diagnostics,
    build_remote_command,
)
from .safety import dispatch_blockers
from .settings import ConfigStore, default_data_dir, validate_settings
from .solar import calculate_solar, panel_target, sample_local_day, validate_coordinates
from .ssh_runner import RunnerResult, SSHCommandRunner
from .state import RuntimeState, settings_revision
from .timezone_utils import LocalTimeError, parse_aware_timestamp, resolve_local_datetime


STATIC_DIR = Path(__file__).parent / "static"


def _timestamp_from_body(body: dict[str, Any], default_timezone: str | None = None) -> datetime:
    if "timestamp" in body:
        value = body["timestamp"]
        if not isinstance(value, str):
            raise ValueError("timestamp must be an ISO 8601 string with an offset")
        return parse_aware_timestamp(value)
    timezone_name = body.get("timezone", default_timezone)
    local_value = body.get("local_datetime")
    if not isinstance(timezone_name, str) or not isinstance(local_value, str):
        raise ValueError("Provide an offset-aware timestamp or local_datetime and IANA timezone")
    fold = body.get("fold")
    if fold is not None and (type(fold) is not int or fold not in (0, 1)):
        raise ValueError("fold must be 0 or 1")
    return resolve_local_datetime(local_value, timezone_name, fold)


def _site_is_configured(settings: dict[str, Any]) -> bool:
    site = settings["installation"]
    return site["latitude"] is not None and site["longitude"] is not None


def _cli_reported_publication(output: str, servo_id: int, pulse: int) -> bool:
    beginning_marker = "publisher: beginning loop"
    lines = [line.strip() for line in (output or "").splitlines() if line.strip()]
    beginning_lines = [index for index, line in enumerate(lines) if line == beginning_marker]
    publication_lines = [line for line in lines if line.startswith("publishing #")]
    if len(beginning_lines) != 1 or len(publication_lines) != 1:
        return False
    publication = re.fullmatch(r"publishing #(\d+):\s*(.*)", publication_lines[0])
    if publication is None or publication.group(1) != "1":
        return False
    publication_index = lines.index(publication_lines[0])
    if beginning_lines[0] > publication_index:
        return False
    for line in lines:
        if line in {beginning_marker, publication_lines[0]}:
            continue
        if re.fullmatch(r"Waiting for at least 1 matching subscription\(s\)\.\.\.", line):
            continue
        return False
    message = publication.group(2)
    id_match = re.search(rf"\bid\s*=\s*{servo_id}(?!\d)", message)
    pulse_match = re.search(rf"\bposition\s*=\s*{pulse}(?!\d)", message)
    return id_match is not None and pulse_match is not None


def _preview(
    latitude: float,
    longitude: float,
    timestamp: datetime,
    settings: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    solar = calculate_solar(latitude, longitude, timestamp)
    target = panel_target(solar, settings["operation"]["daylight_threshold_deg"])
    mapped: dict[str, Any] | None = None
    mapping_error: str | None = None
    if target["target_azimuth_deg"] is not None:
        try:
            mapped = map_targets(
                target["target_azimuth_deg"], target["target_tilt_deg"], settings["calibration"]
            )
        except ValueError as error:
            mapping_error = str(error)
            target["status"] = "TARGET_UNREACHABLE"
    commands = mapped["servo_commands"] if mapped else None
    blockers = dispatch_blockers(settings, commands) if commands else [target["status"]]
    hardware_ready = commands is not None and not blockers
    if mode == "simulate":
        blockers = [*blockers, "SIMULATION_MODE_NO_DISPATCH"]
        hardware_ready = False
    local = timestamp.astimezone(ZoneInfo(settings["installation"]["timezone"]))
    result = {
        "mode": mode,
        "status": target["status"],
        "local_time": local.isoformat(),
        "fold": local.fold,
        "timezone_abbreviation": local.tzname(),
        "utc_time": timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "latitude": latitude,
        "longitude": longitude,
        "solar": solar,
        "target": target,
        "servo_commands": commands,
        "manual_commands": build_manual_commands(commands[0]["position"], commands[1]["position"])
        if commands
        else None,
        "calibration_verified": bool(mapped and mapped["calibration_verified"]),
        "mapping_error": mapping_error,
        "dispatch_blockers": blockers,
        "hardware_ready": hardware_ready,
        "last_requested": None,
        "actual_position": "UNKNOWN",
        "motion_confirmed": False,
    }
    return result


def create_app(
    data_dir: Path | str | None = None,
    runner: Any | None = None,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    store = ConfigStore(data_root)
    runtime = RuntimeState(data_root, store)
    command_runner = runner or SSHCommandRunner()
    clock_now = clock or (lambda: datetime.now(UTC))
    application = FastAPI(title="SolarMind", docs_url=None, redoc_url=None, openapi_url=None)
    application.state.runtime = runtime
    application.state.runner = command_runner
    application.state.clock = clock_now
    application.state.csrf_token = secrets.token_urlsafe(32)

    @application.middleware("http")
    async def local_origin_guard(request: Request, call_next: Callable[..., Any]) -> Any:
        if request.url.path.startswith("/api/"):
            hostname = (request.url.hostname or "").lower()
            if hostname not in {"127.0.0.1", "localhost"}:
                return JSONResponse({"detail": "SolarMind API accepts loopback requests only"}, status_code=403)
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                origin = request.headers.get("origin")
                host = request.headers.get("host", "")
                parsed_origin = urlsplit(origin or "")
                token = request.headers.get("x-csrf-token", "")
                if (
                    parsed_origin.scheme != "http"
                    or parsed_origin.netloc.casefold() != host.casefold()
                    or not hmac.compare_digest(token, application.state.csrf_token)
                ):
                    return JSONResponse({"detail": "Same-origin request token is missing or invalid"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
        )
        return response

    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/api/bootstrap")
    async def bootstrap() -> dict[str, Any]:
        settings = runtime.get_settings()
        return {
            "csrf_token": application.state.csrf_token,
            "settings": settings,
            "server_now_utc": clock_now().astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "dry_run": settings["operation"]["dry_run"],
            "hardware_enabled": settings["operation"]["hardware_enabled"],
        }

    @application.get("/api/health")
    async def health() -> dict[str, Any]:
        settings = runtime.get_settings()
        return {
            "status": "OK",
            "loopback_only": True,
            "dry_run": settings["operation"]["dry_run"],
            "hardware_enabled": settings["operation"]["hardware_enabled"],
            "ssh_alias_configured": bool(settings["ssh"]["alias"]),
            "installation_configured": _site_is_configured(settings),
        }

    @application.get("/api/live")
    async def live() -> dict[str, Any]:
        settings = runtime.get_settings()
        if not _site_is_configured(settings):
            return {
                "mode": "live",
                "status": "SITE_NOT_CONFIGURED",
                "installation": settings["installation"],
                "actual_position": "UNKNOWN",
                "motion_confirmed": False,
            }
        timestamp = clock_now().astimezone(UTC)
        try:
            result = _preview(
                settings["installation"]["latitude"],
                settings["installation"]["longitude"],
                timestamp,
                settings,
                "live",
            )
        except (ValueError, LocalTimeError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        result["installation"] = settings["installation"]
        result["last_requested"] = runtime.last_command()
        result["dry_run"] = settings["operation"]["dry_run"]
        result["hardware_enabled"] = settings["operation"]["hardware_enabled"]
        return result

    @application.post("/api/settings")
    async def save_settings(body: dict[str, Any]) -> dict[str, Any]:
        try:
            settings = runtime.save_settings(body)
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"status": "SETTINGS_SAVED", "settings": settings}

    @application.post("/api/solar")
    async def solar(body: dict[str, Any]) -> dict[str, Any]:
        try:
            latitude, longitude = validate_coordinates(body.get("latitude"), body.get("longitude"))
            timestamp = _timestamp_from_body(body)
            settings = runtime.get_settings()
            if isinstance(body.get("timezone"), str):
                settings["installation"]["timezone"] = body["timezone"]
            result = _preview(latitude, longitude, timestamp, settings, "simulate")
            result["installation_timezone"] = body.get("timezone")
            result["dispatch_allowed"] = False
            return result
        except (ValueError, LocalTimeError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.post("/api/preview")
    async def preview(body: dict[str, Any]) -> dict[str, Any]:
        mode = body.get("mode")
        if mode not in ("live", "simulate"):
            raise HTTPException(status_code=422, detail="mode must be live or simulate")
        try:
            if mode == "live":
                settings = runtime.get_settings()
                if not _site_is_configured(settings):
                    raise ValueError("Installation coordinates are not configured")
                latitude = settings["installation"]["latitude"]
                longitude = settings["installation"]["longitude"]
                timestamp = clock_now().astimezone(UTC)
            else:
                latitude, longitude = validate_coordinates(body.get("latitude"), body.get("longitude"))
                timestamp = _timestamp_from_body(body)
                settings = runtime.get_settings()
                if isinstance(body.get("timezone"), str):
                    settings["installation"]["timezone"] = body["timezone"]
            return _preview(latitude, longitude, timestamp, settings, mode)
        except (ValueError, LocalTimeError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.post("/api/simulate/day")
    async def simulate_day(body: dict[str, Any]) -> dict[str, Any]:
        try:
            latitude, longitude = validate_coordinates(body.get("latitude"), body.get("longitude"))
            timezone_name = body.get("timezone")
            if not isinstance(timezone_name, str):
                raise ValueError("timezone must be an IANA timezone name")
            day_value = body.get("date")
            if not isinstance(day_value, str):
                raise ValueError("date must be YYYY-MM-DD")
            selected_day = date.fromisoformat(day_value)
            settings = runtime.get_settings()
            interval = body.get("interval_minutes", 15)
            if type(interval) is not int:
                raise ValueError("interval_minutes must be an integer")
            result = sample_local_day(
                latitude,
                longitude,
                selected_day,
                timezone_name,
                settings["operation"]["daylight_threshold_deg"],
                interval,
            )
            for sample in result["samples"]:
                if sample["target_azimuth_deg"] is None:
                    sample["servo_commands"] = None
                    sample["manual_commands"] = None
                    continue
                try:
                    mapped = map_targets(
                        sample["target_azimuth_deg"],
                        sample["target_tilt_deg"],
                        settings["calibration"],
                    )
                    sample["servo_commands"] = mapped["servo_commands"]
                    sample["manual_commands"] = build_manual_commands(
                        mapped["servo_commands"][0]["position"],
                        mapped["servo_commands"][1]["position"],
                    )
                except ValueError as error:
                    sample["status"] = "TARGET_UNREACHABLE"
                    sample["mapping_error"] = str(error)
                    sample["servo_commands"] = None
                    sample["manual_commands"] = None
            return result
        except (ValueError, LocalTimeError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.post("/api/arm/prepare")
    async def prepare_arm() -> dict[str, Any]:
        settings = runtime.get_settings()
        if not _site_is_configured(settings):
            raise HTTPException(status_code=409, detail="Installation coordinates are not configured")
        timestamp = clock_now().astimezone(UTC)
        try:
            calculation = _preview(
                settings["installation"]["latitude"],
                settings["installation"]["longitude"],
                timestamp,
                settings,
                "live",
            )
        except (ValueError, LocalTimeError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        commands = calculation["servo_commands"]
        if not commands or calculation["target"]["status"] != "PREVIEW":
            raise HTTPException(
                status_code=409,
                detail={"status": calculation["target"]["status"], "dispatch_blockers": calculation["dispatch_blockers"]},
            )
        dry_run = settings["operation"]["dry_run"]
        blockers = dispatch_blockers(settings, commands)
        if not dry_run and blockers:
            raise HTTPException(
                status_code=409,
                detail={"status": "DISPATCH_BLOCKED", "dispatch_blockers": blockers},
            )
        try:
            intent = runtime.create_intent(
                {
                    "created_at": timestamp.isoformat().replace("+00:00", "Z"),
                    "target": calculation["target"],
                    "servo_commands": commands,
                    "manual_commands": calculation["manual_commands"],
                    "dry_run": dry_run,
                    "latitude": settings["installation"]["latitude"],
                    "longitude": settings["installation"]["longitude"],
                },
                expected_revision=settings_revision(settings),
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {
            "status": "DRY_RUN_PREPARED" if dry_run else "READY_FOR_EXPLICIT_CONFIRMATION",
            **intent,
            "target": calculation["target"],
            "servo_commands": commands,
            "manual_commands": calculation["manual_commands"],
            "dispatch_blockers": blockers,
            "motion_confirmed": False,
            "actual_position": "UNKNOWN",
        }

    @application.post("/api/arm/one-shot")
    async def one_shot(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        token = body.get("intent_token")
        confirmed = body.get("confirmed")
        if not isinstance(token, str) or len(token) > 100:
            raise HTTPException(status_code=422, detail="A valid intent_token is required")
        if type(confirmed) is not bool or not confirmed:
            raise HTTPException(status_code=400, detail="Explicit operator confirmation is required")
        if not runtime.dispatch_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="Another one-shot sequence is already running")
        try:
            try:
                intent = runtime.consume_intent(token)
            except ValueError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            settings = runtime.get_settings()
            if intent["dry_run"] or settings["operation"]["dry_run"]:
                record = {
                    "request_id": str(uuid.uuid4()),
                    "requested_at": clock_now().astimezone(UTC).isoformat().replace("+00:00", "Z"),
                    "status": "DRY_RUN",
                    "cli_status": "NOT_RUN",
                    "steps": [],
                    "servo_commands": intent["servo_commands"],
                    "manual_commands": intent["manual_commands"],
                    "motion_confirmed": False,
                    "actual_position": "UNKNOWN",
                }
                runtime.record_command(record)
                return record
            blockers = dispatch_blockers(settings, intent["servo_commands"])
            if blockers:
                raise HTTPException(status_code=409, detail={"status": "DISPATCH_BLOCKED", "dispatch_blockers": blockers})
            request_id = str(uuid.uuid4())
            steps: list[dict[str, Any]] = []
            stop_reason: str | None = None
            alias = settings["ssh"]["alias"]
            setup_path = settings["ssh"]["ros_setup_path"]
            for command in intent["servo_commands"]:
                if await request.is_disconnected():
                    stop_reason = "BROWSER_DISCONNECTED"
                    break
                servo_id = command["id"]
                remote = build_remote_command(servo_id, command["position"], setup_path)
                try:
                    result: RunnerResult = await asyncio.to_thread(command_runner.run, alias, remote)
                except Exception as error:
                    result = RunnerResult(1, "", f"SSH runner failed: {type(error).__name__}")
                publication_confirmed = (
                    not result.timed_out
                    and result.exit_code == 0
                    and _cli_reported_publication(result.stdout, servo_id, command["position"])
                )
                step = {
                    "servo_id": servo_id,
                    "position": command["position"],
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "cli_status": (
                        "CLI_RETURNED_SUCCESS"
                        if publication_confirmed
                        else "CLI_OUTPUT_UNRECOGNIZED"
                        if result.exit_code == 0 and not result.timed_out
                        else "CLI_FAILED"
                    ),
                    "publication_confirmed": publication_confirmed,
                    "message": (
                        "SSH command timed out"
                        if result.timed_out
                        else "SSH or ROS CLI returned a nonzero exit code"
                        if result.exit_code != 0
                        else "ROS CLI output did not confirm the requested one-shot publication"
                        if not publication_confirmed
                        else ""
                    ),
                }
                steps.append(step)
                if not publication_confirmed:
                    runtime.invalidate_assumed_pulse(servo_id)
                    break
                runtime.update_assumed_pulse(servo_id, command["position"])
            if len(steps) == 2 and all(step["publication_confirmed"] for step in steps):
                status = "COMMAND_PUBLISHED"
                cli_status = "CLI_RETURNED_SUCCESS"
            elif steps and steps[0]["publication_confirmed"]:
                status = "PARTIAL_DISPATCH"
                cli_status = "PARTIAL"
            elif stop_reason:
                status = "DISPATCH_NOT_STARTED"
                cli_status = "NOT_RUN"
            else:
                status = "DISPATCH_FAILED"
                cli_status = "FAILED"
            record = {
                "request_id": request_id,
                "requested_at": clock_now().astimezone(UTC).isoformat().replace("+00:00", "Z"),
                "status": status,
                "cli_status": cli_status,
                "steps": steps,
                "servo_commands": intent["servo_commands"],
                "stop_reason": stop_reason,
                "motion_confirmed": False,
                "actual_position": "UNKNOWN",
            }
            runtime.record_command(record)
            return record
        finally:
            runtime.dispatch_lock.release()

    @application.get("/api/arm/last-command")
    async def last_command() -> dict[str, Any]:
        record = runtime.last_command()
        return {"status": "NO_COMMAND_REQUESTED", "actual_position": "UNKNOWN"} if record is None else record

    @application.post("/api/connection/check")
    async def connection_check() -> dict[str, Any]:
        settings = runtime.get_settings()
        alias = settings["ssh"]["alias"]
        if not alias:
            return {"status": "SSH_ALIAS_NOT_CONFIGURED", "read_only": True}
        command = build_read_only_diagnostics(settings["ssh"]["ros_setup_path"])
        try:
            result: RunnerResult = await asyncio.to_thread(command_runner.run, alias, command)
        except Exception as error:
            result = RunnerResult(1, "", f"SSH runner failed: {type(error).__name__}")
        return {
            "status": "CONNECTION_CHECKED" if result.exit_code == 0 else "CONNECTION_FAILED",
            "read_only": True,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "output": (result.stdout or result.stderr or "")[:2000],
        }

    @application.exception_handler(ValueError)
    async def value_error_handler(request: Request, error: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=422)

    return application


app = create_app()
