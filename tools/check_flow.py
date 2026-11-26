from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.test import BotTestEnvironment

from app import AppContext
from config import load_settings
from handlers import router
from hh_client import HHClient
from storage import Storage


def last_bot_message(env, user):
    messages = [m for m in user.chat.messages if m.from_user and m.from_user.is_bot]
    return messages[-1] if messages else None


async def main() -> None:
    base = load_settings()
    settings = base.__class__(
        bot_token="42:TEST",
        hh_token=None,
        owner_id=None,
        proxy_url=None,
        db_path=Path(tempfile.gettempdir()) / "hh_bot_flow.sqlite3",
        batch_size=2,
        message_delay=0.05,
        page_delay=0.05,
        max_pages=3,
        request_timeout=35,
    )
    db = Storage(settings.db_path)
    for entry in db.blacklist_list(1000):
        db.blacklist_remove(1000, entry["id"])
    hh = HHClient(settings)
    app = AppContext(settings=settings, db=db, hh=hh)

    dispatcher = Dispatcher(storage=MemoryStorage(), app=app)
    dispatcher.include_router(router)

    env = BotTestEnvironment(dispatcher=dispatcher, default_wait_timeout=20)
    user = env.user(1000)

    try:
        await user.send("/start")
        message = last_bot_message(env, user)
        print("START:", message.text.splitlines()[0] if message else None)
        print("BUTTONS:", [b.callback_data for row in message.reply_markup.inline_keyboard for b in row] if message and message.reply_markup else None)

        await user.click("area:pop:0")
        message = last_bot_message(env, user)
        print("CITY CLICK ->", message.text.splitlines()[0] if message else None)

        await user.send("водитель")
        message = last_bot_message(env, user)
        print("TRANSPORT REJECT:", "Эта профессия исключена" in (message.text or ""))
        print("STATE AFTER TRANSPORT QUERY:", await user.state().get_state())

        await user.send("повар")
        message = last_bot_message(env, user)
        print("QUERY ->", message.text.splitlines()[0] if message else None)

        await user.send("80000")
        message = last_bot_message(env, user)
        print("SALARY ->", message.text.splitlines()[0] if message else None)

        await user.click("exp:noExperience")
        message = last_bot_message(env, user)
        print("EXP ->", message.text.splitlines()[0] if message else None)

        await user.click("sched:FIVE_ON_TWO_OFF")
        message = last_bot_message(env, user)
        print("SCHED ->", message.text.splitlines()[0] if message else None)

        await user.click("hours:HOURS_8")
        message = last_bot_message(env, user)
        print("HOURS ->", (message.text or "").splitlines()[0] if message else None)
        print("SUMMARY BUTTONS:", [b.callback_data for row in message.reply_markup.inline_keyboard for b in row] if message and message.reply_markup else None)

        await user.click("go:start")
        run = app.active.get(1000)
        if not run:
            print("SEARCH NOT STARTED")
            return
        for _ in range(400):
            if run.paused or not run.running:
                break
            await asyncio.sleep(0.05)

        print(f"SEARCH: sent={run.sent}, paused={run.paused}, running={run.running}")
        bot_messages = [m for m in user.chat.messages if m.from_user and m.from_user.is_bot]
        print("LAST BOT TEXTS:")
        for m in bot_messages[-4:]:
            print("  -", (m.text or "").splitlines()[0][:90])

        # Продолжаем поиск ещё на одну пачку
        await user.click("search:resume", message=bot_messages[-1])
        for _ in range(400):
            if run.paused or not run.running:
                break
            await asyncio.sleep(0.05)
        print(f"AFTER RESUME: sent={run.sent}, paused={run.paused}, running={run.running}")
        bot_messages = [m for m in user.chat.messages if m.from_user and m.from_user.is_bot]
        print("LAST BOT TEXTS AFTER RESUME:")
        for m in bot_messages[-3:]:
            print("  -", (m.text or "").splitlines()[0][:90])

        # Останавливаем поиск
        await user.click("search:stop", message=bot_messages[-1])
        print("AFTER STOP: active =", len(app.active))

        # Проверяем избранное: добавляем первую попавшуюся вакансию
        added = None
        for m in bot_messages:
            if m.reply_markup:
                for row in m.reply_markup.inline_keyboard:
                    for b in row:
                        if (b.callback_data or "").startswith("fav:add:"):
                            added = b.callback_data
                            break
                    if added:
                        break
            if added:
                break
        if added:
            print("ADD FAV:", added)
            await user.click(added, message=m)
            print("FAV COUNT:", db.favorite_count(1000))
            await user.send("/favorites")
            message = last_bot_message(env, user)
            print("FAV VIEW:", (message.text or "").splitlines()[0] if message else None)
            print("FAV BUTTONS:", [b.callback_data for row in message.reply_markup.inline_keyboard for b in row] if message and message.reply_markup else None)
            await user.click("fav:del", message=message)
            message = last_bot_message(env, user)
            print("AFTER DELETE:", (message.text or "").splitlines()[0] if message else None)
            print("FAV COUNT AFTER:", db.favorite_count(1000))
        else:
            print("NO FAV BUTTON FOUND")

        # /start сбрасывает опрос и снова спрашивает город
        await user.send("/start")
        await user.click("area:pop:0")
        await user.send("python")
        message = last_bot_message(env, user)
        print("IT REJECT:", "IT-профессия" in (message.text or ""))
        print("STATE AFTER IT QUERY:", await user.state().get_state())

        await user.send("курьер")
        message = last_bot_message(env, user)
        print("COURIER REJECT:", "Эта профессия исключена" in (message.text or ""))
        print("STATE AFTER COURIER QUERY:", await user.state().get_state())

        # Ветка «Все профессии» + пропуск зарплаты и фильтров
        await user.click("q:all")
        await user.click("salary:skip")
        await user.click("exp:any")
        await user.click("sched:any")
        await user.click("hours:any")
        print("STATE AFTER ALL PROFESSIONS:", await user.state().get_state())
        summaries = [
            m.text
            for m in user.chat.messages
            if m.from_user and m.from_user.is_bot and "Параметры поиска" in (m.text or "")
        ]
        print("ALL PROFESSIONS SUMMARY:", bool(summaries), "|", summaries[-1].splitlines()[0] if summaries else None)

        # Чёрный список: открыть, добавить, удалить
        await user.send("/blacklist")
        message = last_bot_message(env, user)
        print("BLACKLIST EMPTY:", "Список пуст" in (message.text or ""))
        await user.click("bl:add:0", message=message)
        message = last_bot_message(env, user)
        print("BLACKLIST ADD PROMPT:", "Добавить в чёрный список" in (message.text or ""))
        await user.send("мойщик")
        message = last_bot_message(env, user)
        print("BLACKLIST ADDED:", "Добавлено" in (message.text or ""), "| count:", db.blacklist_count(1000))
        entries = db.blacklist_list(1000)
        if entries:
            entry_id = entries[0]["id"]
            await user.click(f"bl:del:{entry_id}:0", message=message)
            message = last_bot_message(env, user)
            print("BLACKLIST DELETED:", "Удалено" in (message.text or ""), "| count:", db.blacklist_count(1000))
    finally:
        await env.dispose()
        await hh.close()
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
