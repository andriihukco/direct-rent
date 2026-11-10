"""Run a long-lived task forever, restarting it with exponential backoff when it fails."""
import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable

log = logging.getLogger("directrent.supervisor")

SOURCE_HEALTH: dict[str, dict] = {}
HEALTHY_RESET_S = 600


async def supervise(name: str, start: Callable[[], Awaitable[None]], min_delay: float = 5.0,
                    max_delay: float = 300.0, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
    """Never returns normally; cancellation propagates. A task that returns is restarted too."""
    health = SOURCE_HEALTH.setdefault(name, {"restarts": 0, "last_error": None})
    delay = min_delay
    while True:
        started = time.monotonic()
        try:
            await start()
            error = "returned"
        except Exception as e:  # noqa: BLE001 - a supervisor must survive any task failure
            error = f"{type(e).__name__}: {e}"
        if time.monotonic() - started > HEALTHY_RESET_S:
            delay = min_delay
        health["restarts"] += 1
        health["last_error"] = error
        log.warning(json.dumps({"event": "task_restart", "task": name, "error": error, "delay_s": delay}))
        await sleep(delay)
        delay = min(delay * 2, max_delay)
