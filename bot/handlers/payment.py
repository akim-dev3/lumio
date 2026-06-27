"""Telegram Stars purchase flow."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from bot.db import queries


logger = logging.getLogger(__name__)
router = Router(name="payment")


@dataclass(frozen=True)
class Plan:
    code: str            # used in invoice payload
    title: str
    description: str
    stars: int
    kind: str            # 'credits' | 'pro'
    credits: int = 0     # for 'credits' plans
    days: int = 0        # for 'pro' plans


PLANS: dict[str, Plan] = {
    "credits20": Plan(
        code="credits20",
        title="+20 запросов",
        description="20 дополнительных запросов одноразово. Без срока действия.",
        stars=99,
        kind="credits",
        credits=20,
    ),
    "pro30": Plan(
        code="pro30",
        title="LUMIO Pro — 30 дней",
        description="Безлимит на все 4 инструмента в течение 30 дней.",
        stars=299,
        kind="pro",
        days=30,
    ),
    "pro180": Plan(
        code="pro180",
        title="LUMIO Pro — 180 дней",
        description="Безлимит на 180 дней. Лучшее соотношение цены и срока.",
        stars=999,
        kind="pro",
        days=180,
    ),
}


def plans_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"⭐ {plan.stars} — {plan.title}",
            callback_data=f"buy:{plan.code}",
        )]
        for plan in PLANS.values()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


PLANS_TEXT = (
    "<b>Тарифы LUMIO</b>\n\n"
    "⭐ <b>99</b> — +20 запросов (разово)\n"
    "⭐ <b>299</b> — Pro 30 дней (безлимит)\n"
    "⭐ <b>999</b> — Pro 180 дней (безлимит)\n\n"
    "Оплата через Telegram Stars в один тап.\n"
    "Выбери план 👇"
)


@router.message(Command("plans"))
async def cmd_plans(message: Message) -> None:
    await message.answer(PLANS_TEXT, reply_markup=plans_kb())


@router.callback_query(F.data == "show_plans")
async def cb_show_plans(query: CallbackQuery) -> None:
    if query.message:
        await query.message.answer(PLANS_TEXT, reply_markup=plans_kb())
    await query.answer()


@router.callback_query(F.data == "show_status")
async def cb_show_status(query: CallbackQuery) -> None:
    from bot.services import limits  # local import: avoid circular load

    if query.from_user is None or query.message is None:
        await query.answer()
        return
    await queries.upsert_user(query.from_user.id, query.from_user.username)
    status = await limits.get_status(query.from_user.id)
    if status.plan == "pro":
        text = (
            "💎 <b>Pro</b> активен.\n"
            f"Действует до: <code>{status.plan_expires or '—'}</code>"
        )
    else:
        text = (
            "🆓 <b>Free</b> тариф.\n"
            f"Осталось сегодня: <b>{status.remaining}</b> из {limits.FREE_DAILY_LIMIT}\n\n"
            "Купить безлимит: /plans"
        )
    await query.message.answer(text)
    await query.answer()


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(query: CallbackQuery) -> None:
    code = (query.data or "").split(":", 1)[1]
    plan = PLANS.get(code)
    if plan is None or query.message is None or query.bot is None:
        await query.answer("План не найден", show_alert=True)
        return

    await query.bot.send_invoice(
        chat_id=query.message.chat.id,
        title=plan.title,
        description=plan.description,
        payload=f"plan:{plan.code}",
        provider_token="",  # empty for Telegram Stars
        currency="XTR",
        prices=[LabeledPrice(label=plan.title, amount=plan.stars)],
    )
    await query.answer()


@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout: PreCheckoutQuery) -> None:
    # Always approve — funds settle after this.
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    user = message.from_user
    if payment is None or user is None:
        return

    payload = payment.invoice_payload or ""
    if not payload.startswith("plan:"):
        logger.warning("Unknown payment payload: %s", payload)
        await message.answer("Платёж получен, но план не распознан. Напиши в поддержку.")
        return

    plan = PLANS.get(payload.split(":", 1)[1])
    if plan is None:
        logger.warning("Unknown plan code: %s", payload)
        await message.answer("Платёж получен, но план не найден. Напиши в поддержку.")
        return

    await queries.upsert_user(user.id, user.username)
    await queries.log_transaction(user.id, plan.stars, plan.code)

    if plan.kind == "pro":
        expires = await queries.set_pro_plan(user.id, plan.days)
        await message.answer(
            f"💎 <b>{plan.title}</b> активирован!\n"
            f"Безлимит до <code>{expires.strftime('%Y-%m-%d %H:%M UTC')}</code>.\n\n"
            "Открой Mini App и пользуйся без ограничений 🚀"
        )
    else:
        await queries.add_one_time_credits(user.id, plan.credits)
        await message.answer(
            f"✨ +{plan.credits} запросов начислено.\n"
            "Открой Mini App и пользуйся 🚀"
        )
