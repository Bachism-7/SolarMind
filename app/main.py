"""Loopback-only FastAPI site that reports the position of the sun."""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, date
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import serial_link
from .solar import calculate_solar, sample_local_day, validate_coordinates
from .timezone_utils import LocalTimeError, get_zone, parse_aware_timestamp


STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    application = FastAPI(title="SolarMind", docs_url=None, redoc_url=None, openapi_url=None)

    @application.middleware("http")
    async def local_origin_guard(request: Request, call_next: Callable[..., Any]) -> Any:
        if request.url.path.startswith("/api/"):
            if (request.url.hostname or "").lower() not in {"127.0.0.1", "localhost"}:
                return JSONResponse({"detail": "SolarMind API accepts loopback requests only"}, status_code=403)
        return await call_next(request)

    send_lock = threading.Lock()

    @application.get("/api/serial")
    async def serial_info() -> dict[str, Any]:
        cfg = serial_link.load_config()
        return {
            "port": cfg.PORT,
            "baudrate": cfg.BAUDRATE,
            "ports": serial_link.available_ports(),
            "login_configured": cfg.configured,
        }

    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.post("/api/solar")
    async def solar(body: dict[str, Any]) -> dict[str, Any]:
        """Sun position and panel tilt at one UTC timestamp."""
        try:
            latitude, longitude = validate_coordinates(body.get("latitude"), body.get("longitude"))
            value = body.get("timestamp")
            if not isinstance(value, str):
                raise ValueError("timestamp (ISO 8601 with offset) is required")
            timestamp = parse_aware_timestamp(value)
            sun = calculate_solar(latitude, longitude, timestamp)
            return {
                "utc_time": timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                **sun,
                "tilt_deg": 90.0 - sun["apparent_elevation_deg"] if sun["apparent_elevation_deg"] > 0 else None,
            }
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.post("/api/day")
    async def day(body: dict[str, Any]) -> dict[str, Any]:
        """Sun positions across one UTC calendar day."""
        try:
            latitude, longitude = validate_coordinates(body.get("latitude"), body.get("longitude"))
            day_value = body.get("date")
            if not isinstance(day_value, str):
                raise ValueError("date (YYYY-MM-DD) is required")
            return sample_local_day(latitude, longitude, date.fromisoformat(day_value), "UTC", interval_minutes=10)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.post("/api/send")
    async def send(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Work out servo pulses for the sun at `timestamp`; send them over serial only if send=true."""
        try:
            latitude, longitude = validate_coordinates(body.get("latitude"), body.get("longitude"))
            value = body.get("timestamp")
            if not isinstance(value, str):
                raise ValueError("timestamp (ISO 8601 with offset) is required")
            sun = calculate_solar(latitude, longitude, parse_aware_timestamp(value))
            if sun["apparent_elevation_deg"] <= 0:
                raise ValueError("The sun is below the horizon at that time; nothing to point at")
            cfg = serial_link.load_config()
            tilt = 90.0 - sun["apparent_elevation_deg"]
            commands = serial_link.servo_pulses(sun["azimuth_deg"], tilt, cfg)
            lines = [serial_link.pulse_command(c["id"], c["position"]) for c in commands]
            result: dict[str, Any] = {"servo_commands": commands, "cli_commands": lines, "sent": False}
            if body.get("send") is not True:
                return result
            origin = request.headers.get("origin", "")
            if origin.split("://", 1)[-1] != request.headers.get("host", ""):
                raise PermissionError("Same-origin requests only")
            port = body.get("port") or cfg.PORT
            if not isinstance(port, str):
                raise ValueError("port must be a string such as COM7")
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if not send_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="Another send is already running")

        def work() -> list[dict[str, Any]]:
            steps: list[dict[str, Any]] = []
            with serial_link.SerialSession(port, cfg) as link:
                link.login()
                for command, line in zip(commands, lines):
                    output = link.run(line)
                    ok = "publishing #1" in output
                    steps.append({"servo_id": command["id"], "position": command["position"],
                                  "published": ok, "output": output[-1500:]})
                    if not ok:
                        break
            return steps

        try:
            result["steps"] = await asyncio.to_thread(work)
        except serial_link.SerialError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        finally:
            send_lock.release()
        result["sent"] = True
        result["all_published"] = len(result["steps"]) == len(commands) and all(s["published"] for s in result["steps"])
        return result

    return application


app = create_app()
