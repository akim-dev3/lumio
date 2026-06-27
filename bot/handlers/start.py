"""/start onboarding + plan command."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from bot.config import config
from bot.db import queries
from bot.services import limits


router = Router(name="start")


WELCOME = (
    "👋 <b>Привет! Это LUMIO</b> — твой AI-комбайн в одном боте.\n\n"
    "Внутри 4 инструмента:\n"
    "🎴 <b>Anki Cards</b> — карточки из любого текста\n"
    "✍️ <b>TG Copywriter</b> — посты для каналов\n"
    "📄 <b>PDF Analyst</b> — конспект и вопросы по PDF\n"
    "💼 <b>Resume Builder</b> — резюме и cover letter под вакансию\n\n"
    "🎁 Бесплатно: <b>3 запроса в день</b>.\n"
    "⭐ Pro: безлимит на 30 или 180 дней через Telegram Stars.\n\n"
    "Жми кнопку ниже и поехали 👇"
)


def webapp_reply_kb() -> ReplyKeyboardMarkup:
    """Reply keyboard with the WebApp launcher.

    A reply-keyboard WebApp button is required so the Mini App can post results
    back via ``Telegram.WebApp.sendData()`` — inline-keyboard WebApp buttons
    cannot send data back to the bot.
    """
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(
                text="🚀 Open LUMIO",
                web_app=WebAppInfo(url=config.webapp_url),
            )
        ]],
        resize_keyboard=True,
        is_persistent=True,
    )


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐ Тарифы", callback_data="show_plans"),
                InlineKeyboardButton(text="📊 Мой план", callback_data="show_status"),
            ],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    if user is None:
        return
    await queries.upsert_user(user.id, user.username)
    await message.answer(WELCOME, reply_markup=webapp_reply_kb())
    await message.answer("Управление:", reply_markup=main_menu_kb())


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    user = message.from_user
    if user is None:
        return
    await queries.upsert_user(user.id, user.username)
    status = await limits.get_status(user.id)
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
    await message.answer(text, reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start — главное меню\n"
        "/status — текущий план и остаток\n"
        "/plans — купить безлимит за Stars\n\n"
        "Все инструменты внутри Mini App (кнопка «Open LUMIO»).\n"
        "PDF: пришли файл прямо в чат — бот извлечёт текст и подготовит "
        "анализ, который откроется в приложении.",
        reply_markup=main_menu_kb(),
    )
