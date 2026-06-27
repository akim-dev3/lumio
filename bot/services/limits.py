"""Freemium quota checks.

Free tier: 3 successful tool runs per UTC day. Pro tier (paid via Stars):
unlimited until ``plan_expires``. The check runs *before* the AI call and
increments the counter atomically on success.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from bot.db import queries


FREE_DAILY_LIMIT = 3


@dataclass
class LimitDecision:
    allowed: bool
    reason: Optional[str] = None         # 'limit_reached' | None
    remaining: int = 0                   # free-tier remaining requests today
    plan: str = "free"                   # 'free' | 'pro'
    plan_expires: Optional[str] = None   # ISO timestamp for pro tier

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "remaining": self.remaining,
            "plan": self.plan,
            "plan_expires": self.plan_expires,
        }


async def check_and_consume(tg_id: int) -> LimitDecision:
    """Reserve one request slot for ``tg_id``.

    Pro users always pass without touching the counter. Free users get up to
    :data:`FREE_DAILY_LIMIT` calls per UTC day; when allowed, ``daily_count``
    is incremented immediately so concurrent calls cannot exceed the cap.
    """
    await queries.reset_daily_if_needed(tg_id)
    user = await queries.get_user(tg_id)
    if user is None:
        # Should never happen — /start always upserts. Fail closed.
        return LimitDecision(allowed=False, reason="user_not_found")

    if user.is_pro_active:
        return LimitDecision(
            allowed=True,
            plan="pro",
            plan_expires=user.plan_expires.isoformat() if user.plan_expires else None,
        )

    if user.daily_count < FREE_DAILY_LIMIT:
        await queries.increment_daily(tg_id)
        remaining = FREE_DAILY_LIMIT - (user.daily_count + 1)
        return LimitDecision(
            allowed=True,
            plan="free",
            remaining=max(remaining, 0),
        )

    return LimitDecision(
        allowed=False,
        reason="limit_reached",
        plan="free",
        remaining=0,
    )


async def refund(tg_id: int) -> None:
    """Return one slot to a free-tier user. No-op for pro users (they never consumed)."""
    user = await queries.get_user(tg_id)
    if user is None or user.is_pro_active:
        return
    await queries.refund_daily(tg_id)


async def get_status(tg_id: int) -> LimitDecision:
    """Read-only quota snapshot for the UI badge (no counter mutation)."""
    await queries.reset_daily_if_needed(tg_id)
    user = await queries.get_user(tg_id)
    if user is None:
        return LimitDecision(allowed=False, reason="user_not_found")
    if user.is_pro_active:
        return LimitDecision(
            allowed=True,
            plan="pro",
            plan_expires=user.plan_expires.isoformat() if user.plan_expires else None,
        )
    remaining = max(FREE_DAILY_LIMIT - user.daily_count, 0)
    return LimitDecision(allowed=remaining > 0, plan="free", remaining=remaining)
