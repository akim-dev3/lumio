"""Database queries — every read/write the bot needs lives here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from bot.db.database import get_db


@dataclass
class User:
    tg_id: int
    username: Optional[str]
    plan: str
    plan_expires: Optional[datetime]
    daily_count: int
    last_reset: str

    @property
    def is_pro_active(self) -> bool:
        if self.plan != "pro" or self.plan_expires is None:
            return False
        return self.plan_expires > datetime.now(timezone.utc)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    # SQLite stores TIMESTAMP as ISO-ish text. Normalise to aware UTC.
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def upsert_user(tg_id: int, username: Optional[str]) -> User:
    """Insert a user on first contact, otherwise update the username."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO users (tg_id, username)
            VALUES (?, ?)
            ON CONFLICT(tg_id) DO UPDATE SET username = excluded.username
            """,
            (tg_id, username),
        )
        await db.commit()
    user = await get_user(tg_id)
    assert user is not None
    return user


async def get_user(tg_id: int) -> Optional[User]:
    async with get_db() as db:
        async with db.execute(
            "SELECT tg_id, username, plan, plan_expires, daily_count, last_reset "
            "FROM users WHERE tg_id = ?",
            (tg_id,),
        ) as cur:
            row = await cur.fetchone()
    if row is None:
        return None
    return User(
        tg_id=row["tg_id"],
        username=row["username"],
        plan=row["plan"],
        plan_expires=_parse_dt(row["plan_expires"]),
        daily_count=row["daily_count"] or 0,
        last_reset=row["last_reset"] or "",
    )


async def reset_daily_if_needed(tg_id: int) -> None:
    """Zero ``daily_count`` if the stored ``last_reset`` is older than today UTC."""
    today = datetime.now(timezone.utc).date().isoformat()
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET daily_count = 0, last_reset = ? "
            "WHERE tg_id = ? AND (last_reset IS NULL OR last_reset < ?)",
            (today, tg_id, today),
        )
        await db.commit()


async def increment_daily(tg_id: int) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET daily_count = daily_count + 1 WHERE tg_id = ?",
            (tg_id,),
        )
        await db.commit()


async def refund_daily(tg_id: int) -> None:
    """Roll back a previously-consumed free-tier slot when the AI call fails."""
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET daily_count = MAX(daily_count - 1, 0) WHERE tg_id = ?",
            (tg_id,),
        )
        await db.commit()


async def add_one_time_credits(tg_id: int, credits: int) -> None:
    """Subtract ``credits`` from daily_count (effectively granting extra requests today).

    For one-time top-ups we decrement ``daily_count`` so the next ``credits``
    calls always pass the free-tier check.
    """
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET daily_count = MAX(daily_count - ?, -1000) WHERE tg_id = ?",
            (credits, tg_id),
        )
        await db.commit()


async def set_pro_plan(tg_id: int, days: int) -> datetime:
    """Activate pro plan for ``days`` days, extending an existing pro plan if any."""
    now = datetime.now(timezone.utc)
    current = await get_user(tg_id)
    base = current.plan_expires if current and current.is_pro_active else now
    new_expires = base + timedelta(days=days)
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET plan = 'pro', plan_expires = ? WHERE tg_id = ?",
            (new_expires.isoformat(), tg_id),
        )
        await db.commit()
    return new_expires


async def log_transaction(tg_id: int, stars: int, plan: str) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO transactions (tg_id, stars, plan) VALUES (?, ?, ?)",
            (tg_id, stars, plan),
        )
        await db.commit()
