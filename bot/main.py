"""Application entry point — webhook mode for Render.com free tier.

Run locally for development:
    python -m bot.main --polling

Run in production (Render web service):
    python -m bot.main
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import (
    SimpleRequestHandler,
    setup_application,
)
from aiohttp import web

from bot.config import config
from bot.db.database import init_db
from bot.handlers import payment, start, webapp


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(payment.router)
    dp.include_router(webapp.router)
    return dp


def build_bot() -> Bot:
    return Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def _on_startup(bot: Bot) -> None:
    await init_db()
    await bot.set_webhook(
        url=config.full_webhook_url,
        secret_token=config.webhook_secret,
        allowed_updates=[
            "message",
            "callback_query",
            "pre_checkout_query",
        ],
        drop_pending_updates=True,
    )
    logger.info("Webhook set to %s", config.full_webhook_url)


async def _on_shutdown(bot: Bot) -> None:
    await bot.delete_webhook(drop_pending_updates=False)
    await bot.session.close()


async def _healthcheck(_: web.Request) -> web.Response:
    return web.Response(text="ok")


def run_webhook() -> None:
    bot = build_bot()
    dp = build_dispatcher()

    dp.startup.register(_on_startup)
    dp.shutdown.register(_on_shutdown)

    app = web.Application()
    app.router.add_get("/", _healthcheck)
    app.router.add_get("/health", _healthcheck)

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=config.webhook_secret,
    ).register(app, path=config.webhook_path)

    setup_application(app, dp, bot=bot)

    web.run_app(app, host="0.0.0.0", port=config.port)


async def run_polling() -> None:
    """Local development helper. Not used in production."""
    bot = build_bot()
    dp = build_dispatcher()
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Starting polling…")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="lumio-bot")
    parser.add_argument(
        "--polling",
        action="store_true",
        help="Run in long-polling mode (local dev). Default is webhook.",
    )
    args = parser.parse_args()

    if args.polling:
        try:
            asyncio.run(run_polling())
        except (KeyboardInterrupt, SystemExit):
            logger.info("Polling stopped.")
        return

    run_webhook()


if __name__ == "__main__":
    main()
