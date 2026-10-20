"""Local configuration, one-use intents, and minimal command audit records."""

from __future__ import annotations

import copy
import hashlib
import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from .settings import ConfigStore


def settings_revision(settings: dict[str, Any]) -> str:
    encoded = json.dumps(settings, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


class RuntimeState:
    def __init__(self, data_dir: Path | str, store: ConfigStore | None = None):
        self.data_dir = Path(data_dir)
        self.store = store or ConfigStore(self.data_dir)
        self.audit_path = self.data_dir / "command-audit.jsonl"
        self._lock = threading.RLock()
        self._dispatch_lock = threading.Lock()
        self._intents: dict[str, dict[str, Any]] = {}
        self._last_command: dict[str, Any] | None = None
        self._last_command_loaded = False

    @property
    def dispatch_lock(self) -> threading.Lock:
        return self._dispatch_lock

    def create_intent(
        self,
        payload: dict[str, Any],
        ttl_seconds: int = 60,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        with self._lock:
            revision = settings_revision(self.store.load())
            if expected_revision is not None and revision != expected_revision:
                raise ValueError("Settings changed while preparing the target; prepare it again")
            self._intents[token] = {
                "payload": copy.deepcopy(payload),
                "revision": revision,
                "expires_at": time.time() + ttl_seconds,
            }
        return {"token": token, "expires_in_seconds": ttl_seconds}

    def consume_intent(self, token: str) -> dict[str, Any]:
        with self._lock:
            intent = self._intents.pop(token, None)
        if intent is None:
            raise ValueError("Intent is unknown or already used")
        if time.time() > intent["expires_at"]:
            raise ValueError("Intent expired; prepare a fresh target")
        if intent["revision"] != settings_revision(self.store.load()):
            raise ValueError("Settings changed after confirmation was prepared")
        return copy.deepcopy(intent["payload"])

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        if not self._dispatch_lock.acquire(blocking=False):
            raise RuntimeError("Settings cannot change while a one-shot sequence is running")
        try:
            return self.store.save(settings)
        finally:
            self._dispatch_lock.release()

    def get_settings(self) -> dict[str, Any]:
        return self.store.load()

    def update_assumed_pulse(self, servo_id: int, pulse: int) -> None:
        settings = self.store.load()
        key = "assumed_azimuth_pulse" if servo_id == 1 else "assumed_tilt_pulse"
        settings["safety"][key] = pulse
        self.store.save(settings)

    def invalidate_assumed_pulse(self, servo_id: int) -> None:
        settings = self.store.load()
        key = "assumed_azimuth_pulse" if servo_id == 1 else "assumed_tilt_pulse"
        settings["safety"][key] = None
        self.store.save(settings)

    def record_command(self, record: dict[str, Any]) -> None:
        safe_record = copy.deepcopy(record)
        with self._lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(safe_record, separators=(",", ":"), allow_nan=False) + "\n")
            self._last_command = safe_record
            self._last_command_loaded = True

    def last_command(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._last_command_loaded:
                try:
                    lines = self.audit_path.read_text(encoding="utf-8").splitlines()
                    if lines:
                        self._last_command = json.loads(lines[-1])
                except (OSError, ValueError):
                    self._last_command = None
                self._last_command_loaded = True
            return copy.deepcopy(self._last_command)
