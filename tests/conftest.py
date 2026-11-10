import os

import asyncpg
import pytest

from directrent.db import create_pool, migrate

TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://dr:dr@localhost:55432/dr_test")


@pytest.fixture
async def fresh_db():
    """A pool on an empty public schema (no migrations applied)."""
    conn = await asyncpg.connect(TEST_DSN)
    await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    await conn.close()
    pool = await create_pool(TEST_DSN)
    yield pool
    await pool.close()


@pytest.fixture
async def db(fresh_db):
    """A pool on a freshly migrated schema."""
    await migrate(fresh_db)
    return fresh_db
