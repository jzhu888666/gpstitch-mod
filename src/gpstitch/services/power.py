"""Host power-management helpers."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ShutdownResult:
    """Result of a host shutdown request."""

    success: bool
    message: str


class PowerService:
    """Schedules host shutdown actions for completed render tasks."""

    def __init__(self) -> None:
        self._triggered_keys: set[str] = set()
        self._lock = asyncio.Lock()

    @staticmethod
    def supports_shutdown() -> bool:
        """Return whether this platform supports the configured shutdown action."""
        return sys.platform == "win32"

    async def schedule_shutdown_once(
        self,
        key: str,
        *,
        delay_seconds: int = 60,
        comment: str = "GPStitch render tasks completed.",
    ) -> ShutdownResult:
        """Schedule Windows shutdown once for a logical key.

        The delay gives the user a visible grace period and allows cancelling
        from a terminal with `shutdown /a` if the option was enabled by mistake.
        """
        async with self._lock:
            if key in self._triggered_keys:
                return ShutdownResult(success=True, message="Shutdown already scheduled.")
            self._triggered_keys.add(key)

        if not self.supports_shutdown():
            message = "Shutdown after render is only supported on Windows."
            logger.warning(message)
            return ShutdownResult(success=False, message=message)

        delay_seconds = max(0, int(delay_seconds))
        shutdown_exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "shutdown.exe"
        executable = str(shutdown_exe) if shutdown_exe.exists() else "shutdown"
        command = [executable, "/s", "/t", str(delay_seconds), "/c", comment]

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
        except Exception as exc:
            message = f"Failed to schedule Windows shutdown: {exc}"
            logger.exception(message)
            return ShutdownResult(success=False, message=message)

        if process.returncode != 0:
            output = (stderr or stdout or b"").decode("utf-8", errors="replace").strip()
            message = f"Windows shutdown command failed: {output or process.returncode}"
            logger.error(message)
            return ShutdownResult(success=False, message=message)

        message = f"Windows shutdown scheduled in {delay_seconds} seconds."
        logger.info(message)
        return ShutdownResult(success=True, message=message)


power_service = PowerService()
