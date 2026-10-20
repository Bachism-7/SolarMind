"""Bounded Windows SSH subprocess runner; never invokes a local shell."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class RunnerResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class SSHCommandRunner:
    """Run one SSH invocation with strict host-key and batch-mode settings."""

    def __init__(self, executable: str | None = None, timeout_seconds: float = 15.0):
        self.executable = executable or shutil.which("ssh") or "ssh"
        self.timeout_seconds = timeout_seconds

    def run(self, alias: str, remote_command: str) -> RunnerResult:
        args = [
            self.executable,
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=yes",
            alias,
            remote_command,
        ]
        try:
            completed = subprocess.run(
                args,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
            return RunnerResult(completed.returncode, completed.stdout, completed.stderr)
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout.decode("utf-8", "replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
            stderr = error.stderr.decode("utf-8", "replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
            return RunnerResult(124, stdout, stderr or "SSH command timed out", timed_out=True)
        except OSError as error:
            return RunnerResult(127, "", f"Could not start SSH: {error}")
