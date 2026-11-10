import asyncpg
import pytest

from directrent.db import migrate


async def test_migrate_is_idempotent(fresh_db):
    assert await migrate(fresh_db) == ["001_init.sql"]
    assert await migrate(fresh_db) == []


async def test_listing_unique_source_id(db):
    q = """INSERT INTO listings (source, source_id, url, text, pets, posted_at, verdict, verdict_stage, verdict_reason)
           VALUES ('telegram', 'ch:1', 'u', 't', 'unknown', now(), 'pass', 'rules', 'x')"""
    await db.execute(q)
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.execute(q)
