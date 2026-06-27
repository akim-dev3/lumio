"""SQLite connection helper and schema migrations."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiosqlite

from bot.config import config


logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    tg_id        INTEGER PRIMARY KEY,
    username     TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    plan         TEXT    DEFAULT 'free',
    plan_expires TIMESTAMP,
    daily_count  INTEGER DEFAULT 0,
    last_reset   DATE    DEFAULT (DATE('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id      INTEGER NOT NULL,
    stars      INTEGER NOT NULL,
    plan       TEXT    NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tg_id) REFERENCES users(tg_id)
);

CREATE INDEX IF NOT EXISTS idx_transactions_tg_id ON transactions(tg_id);
"""


async def init_db() -> None:
    """Create tables if they don't exist."""
    async with aiosqlite.connect(config.database_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    logger.info("Database initialised at %s", config.database_path)


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """Yield a configured aiosqlite connection.

    Rows behave like dicts (``row["plan"]``) via ``aiosqlite.Row``.
    Foreign keys are enforced.
    """
    async with aiosqlite.connect(config.database_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")
        yield db
