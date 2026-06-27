"""Dispatch tool requests from the Mini App and PDF uploads."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    FSInputFile,
    Message,
)

from bot.db import queries
from bot.services import anki_gen, gemini, limits, pdf_parser


logger = logging.getLogger(__name__)
router = Router(name="webapp")


PDF_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


# ----------------------------------------------------------------------------
# WebApp data dispatcher
# ----------------------------------------------------------------------------

@router.message(F.web_app_data)
async def on_web_app_data(message: Message) -> None:
    user = message.from_user
    if user is None or message.web_app_data is None:
        return

    try:
        payload = json.loads(message.web_app_data.data)
    except json.JSONDecodeError:
        await message.answer("⚠️ Не удалось прочитать данные из приложения.")
        return

    tool = (payload.get("tool") or "").strip().lower()
    args = payload.get("payload") or {}
    if not tool:
        await message.answer("⚠️ Не указан инструмент.")
        return

    await queries.upsert_user(user.id, user.username)
    decision = await limits.check_and_consume(user.id)
    if not decision.allowed:
        await _send_paywall(message)
        return

    if tool == "cards":
        await _handle_cards(message, args)
    elif tool == "posts":
        await _handle_posts(message, args)
    elif tool == "resume":
        await _handle_resume(message, args)
    elif tool == "pdf":
        # The PDF workflow runs through the upload handler below.
        await message.answer(
            "📎 Пришли PDF-файл прямо сюда в чат — я разберу его и пришлю анализ."
        )
    else:
        await message.answer(f"⚠️ Неизвестный инструмент: <code>{tool}</code>")


# ----------------------------------------------------------------------------
# Tool handlers
# ----------------------------------------------------------------------------

async def _handle_cards(message: Message, args: dict[str, Any]) -> None:
    text = (args.get("text") or "").strip()
    count = int(args.get("count") or 10)
    if not text:
        await message.answer("⚠️ Пустой текст для карточек.")
        return

    status_msg = await message.answer("🎴 Генерирую карточки…")
    cards = await gemini.generate_cards(text, count)
    if not cards:
        await limits.refund(message.from_user.id)
        await status_msg.edit_text(
            "😔 Не получилось сгенерировать карточки. Попробуй ещё раз — "
            "запрос вернулся в твой дневной лимит."
        )
        return

    apkg_path = None
    try:
        apkg_path = await anki_gen.build_apkg(cards, deck_name="LUMIO Deck")
        preview = "\n\n".join(
            f"<b>{i + 1}. {card['front']}</b>\n{card['back']}"
            for i, card in enumerate(cards[:3])
        )
        await status_msg.edit_text(
            f"✅ Готово, карточек: <b>{len(cards)}</b>\n\n"
            f"<u>Превью:</u>\n{preview}"
        )
        await message.answer_document(
            FSInputFile(str(apkg_path), filename="lumio_deck.apkg"),
            caption="📦 Импортируй файл в Anki — карточки появятся в новой колоде.",
        )
    finally:
        if apkg_path is not None:
            try:
                os.unlink(apkg_path)
            except OSError:
                pass


async def _handle_posts(message: Message, args: dict[str, Any]) -> None:
    topic = (args.get("topic") or "").strip()
    count = int(args.get("count") or 3)
    tone = (args.get("tone") or "casual").strip()
    if not topic:
        await message.answer("⚠️ Не указана тема для постов.")
        return

    status_msg = await message.answer("✍️ Пишу посты…")
    posts = await gemini.generate_posts(topic, count, tone)
    if not posts:
        await limits.refund(message.from_user.id)
        await status_msg.edit_text(
            "😔 Не получилось сгенерировать посты. Попробуй другую тему — "
            "запрос вернулся в твой дневной лимит."
        )
        return

    await status_msg.edit_text(f"✅ Готово, постов: <b>{len(posts)}</b>")
    for i, post in enumerate(posts, 1):
        await message.answer(f"<b>Пост {i}/{len(posts)}</b>\n\n{post}")


async def _handle_resume(message: Message, args: dict[str, Any]) -> None:
    vacancy = (args.get("vacancy") or "").strip()
    experience = (args.get("experience") or "").strip()
    if not vacancy or not experience:
        await message.answer("⚠️ Нужно указать и вакансию, и опыт.")
        return

    status_msg = await message.answer("💼 Готовлю резюме и cover letter…")
    result = await gemini.generate_resume(vacancy, experience)
    if not result:
        await limits.refund(message.from_user.id)
        await status_msg.edit_text(
            "😔 Не получилось сгенерировать резюме. Попробуй ещё раз — "
            "запрос вернулся в твой дневной лимит."
        )
        return

    tips = "\n".join(f"• {t}" for t in result["tips"])
    await status_msg.edit_text("✅ Готово")
    await _send_long(message, "<b>📄 Резюме</b>\n\n" + result["resume"])
    await _send_long(message, "<b>✉️ Cover letter</b>\n\n" + result["cover_letter"])
    await message.answer("<b>💡 Советы</b>\n\n" + tips)


# ----------------------------------------------------------------------------
# PDF upload handler
# ----------------------------------------------------------------------------

@router.message(F.document)
async def on_document(message: Message) -> None:
    doc = message.document
    user = message.from_user
    if doc is None or user is None or message.bot is None:
        return

    mime = doc.mime_type or ""
    name = (doc.file_name or "").lower()
    is_pdf = mime == "application/pdf" or name.endswith(".pdf")
    if not is_pdf:
        await message.answer("⚠️ Поддерживается только PDF.")
        return

    if (doc.file_size or 0) > PDF_MAX_BYTES:
        await message.answer("⚠️ PDF слишком большой. Лимит — 10 МБ.")
        return

    await queries.upsert_user(user.id, user.username)
    decision = await limits.check_and_consume(user.id)
    if not decision.allowed:
        await _send_paywall(message)
        return

    status_msg = await message.answer("📄 Читаю PDF…")
    buf = await message.bot.download(doc.file_id)
    if buf is None:
        await limits.refund(user.id)
        await status_msg.edit_text("😔 Не удалось скачать файл. Запрос вернулся в лимит.")
        return
    data = buf.read()

    text = await pdf_parser.extract_text(data)
    if not text:
        await limits.refund(user.id)
        await status_msg.edit_text(
            "😔 Не получилось извлечь текст из PDF "
            "(возможно, это скан — нужен OCR). Запрос вернулся в лимит."
        )
        return

    await status_msg.edit_text("🤖 Анализирую…")
    analysis = await gemini.analyze_pdf(text)
    if not analysis:
        await limits.refund(user.id)
        await status_msg.edit_text(
            "😔 Анализ не удался. Попробуй другой документ — "
            "запрос вернулся в твой дневной лимит."
        )
        return

    key_points = "\n".join(f"• {p}" for p in analysis["key_points"])
    questions = "\n".join(f"❓ {q}" for q in analysis["questions"])
    body = (
        f"<b>📝 Краткое содержание</b>\n{analysis['summary']}\n\n"
        f"<b>🔑 Ключевые мысли</b>\n{key_points}\n\n"
        f"<b>🤔 Вопросы для проверки</b>\n{questions}"
    )
    await status_msg.edit_text("✅ Готово")
    await _send_long(message, body)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

async def _send_paywall(message: Message) -> None:
    from bot.handlers.payment import plans_kb  # local: avoid circular import

    await message.answer(
        "⛔ <b>Дневной лимит исчерпан</b>\n\n"
        "На free-тарифе доступно 3 запроса в день.\n"
        "Открой безлимит за Telegram Stars 👇",
        reply_markup=plans_kb(),
    )


TG_MESSAGE_LIMIT = 3900  # leave headroom under the 4096 cap


async def _send_long(message: Message, text: str) -> None:
    """Split a long HTML-ish message on paragraph boundaries."""
    if len(text) <= TG_MESSAGE_LIMIT:
        await message.answer(text)
        return
    buf = ""
    for paragraph in text.split("\n\n"):
        chunk = paragraph + "\n\n"
        if len(buf) + len(chunk) > TG_MESSAGE_LIMIT:
            if buf:
                await message.answer(buf.rstrip())
            # Single oversized paragraph: hard-split.
            while len(chunk) > TG_MESSAGE_LIMIT:
                await message.answer(chunk[:TG_MESSAGE_LIMIT])
                chunk = chunk[TG_MESSAGE_LIMIT:]
            buf = chunk
        else:
            buf += chunk
    if buf.strip():
        await message.answer(buf.rstrip())


# Keep BufferedInputFile importable for potential future in-memory sends.
__all__ = ["router", "BufferedInputFile"]
