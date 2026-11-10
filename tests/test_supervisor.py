import asyncio

import pytest

from directrent.supervisor import SOURCE_HEALTH, supervise


async def test_restarts_with_doubling_delay():
    calls, delays = [], []

    async def start():
        calls.append(1)
        if len(calls) <= 2:
            raise RuntimeError(f"fail {len(calls)}")
        raise asyncio.CancelledError

    async def fake_sleep(s):
        delays.append(s)

    with pytest.raises(asyncio.CancelledError):
        await supervise("src", start, sleep=fake_sleep)
    assert delays == [5.0, 10.0]
    assert SOURCE_HEALTH["src"]["restarts"] == 2 and SOURCE_HEALTH["src"]["last_error"] == "RuntimeError: fail 2"


async def test_delay_capped():
    delays = []
    n = 0

    async def start():
        nonlocal n
        n += 1
        if n > 10:
            raise asyncio.CancelledError
        raise RuntimeError("x")

    async def fake_sleep(s):
        delays.append(s)

    with pytest.raises(asyncio.CancelledError):
        await supervise("cap", start, sleep=fake_sleep)
    assert max(delays) == 300.0
