from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, CallbackQuery, Message

from app import AppContext
from config import BASE_DIR, load_settings
from handlers import router
from hh_client import HHClient
from storage import Storage


class AccessMiddleware(BaseMiddleware):
    """Если задан OWNER_ID — бот отвечает только этому пользователю."""

    async def __call__(self, handler, event, data):
        app: AppContext | None = data.get("app")
        user = data.get("event_from_user")
        if app and app.settings.owner_id and user and user.id != app.settings.owner_id:
            if isinstance(event, Message):
                await event.answer("⛔ Это приватный бот.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Это приватный бот.", show_alert=True)
            return None
        return await handler(event, data)


def setup_logging() -> None:
    log_path = BASE_DIR / "bot.log"
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logging.basicConfig(level=logging.INFO, handlers=[console, file_handler])
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def main() -> None:
    setup_logging()
    log = logging.getLogger("hh-job-bot")

    settings = load_settings()
    if not settings.is_configured:
        log.error(
            "Не задан BOT_TOKEN. Скопируйте .env.example в .env и вставьте токен от @BotFather."
        )
        return

    db = Storage(settings.db_path)
    hh = HHClient(settings)
    app = AppContext(settings=settings, db=db, hh=hh)

    session = AiohttpSession(proxy=settings.proxy_url) if settings.proxy_url else None
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True,
        ),
    )
    dispatcher = Dispatcher(storage=MemoryStorage(), app=app)
    dispatcher.message.middleware(AccessMiddleware())
    dispatcher.callback_query.middleware(AccessMiddleware())
    dispatcher.include_router(router)

    try:
        try:
            me = await bot.get_me()
        except Exception as exc:
            log.error(
                "Не удалось подключиться к Telegram API: %s\n"
                "Проверьте интернет. Если Telegram недоступен напрямую, укажите PROXY_URL "
                "в .env (например, http://127.0.0.1:10809).",
                exc,
            )
            return
        log.info("Бот запущен: @%s (%s)", me.username, me.id)
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Задать параметры заново"),
                BotCommand(command="search", description="Начать поиск"),
                BotCommand(command="favorites", description="Избранные вакансии"),
                BotCommand(command="blacklist", description="Чёрный список"),
                BotCommand(command="stop", description="Остановить поиск"),
                BotCommand(command="menu", description="Главное меню"),
                BotCommand(command="help", description="Помощь"),
            ]
        )
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        log.info("Останавливаюсь…")
        await hh.close()
        await bot.session.close()
        db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот остановлен.")
