from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import ui
from hh_client import HHBlockedError, HHError, matches_blacklist
from models import Filters, SearchRun

if TYPE_CHECKING:
    from app import AppContext

log = logging.getLogger(__name__)

BLOCKED_TEXT = (
    "⚠️ <b>hh.ru временно ограничил доступ</b>\n\n"
    "Похоже на капчу или антибот-защиту. Подождите 5–10 минут и попробуйте снова. "
    "Если не помогает — откройте hh.ru в браузере на этом же компьютере, "
    "пройдите проверку и повторите поиск."
)

ERROR_TEXT = (
    "⚠️ <b>Не удалось продолжить поиск</b>\n\n"
    "Произошла ошибка при обращении к hh.ru. Попробуйте запустить поиск ещё раз "
    "через пару минут."
)


def _salary_matches(vacancy, minimum: int | None) -> bool:
    if not minimum:
        return True
    if vacancy.currency and vacancy.currency not in {"RUR", "RUB"}:
        return True
    if vacancy.salary_to is not None:
        return vacancy.salary_to >= minimum
    if vacancy.salary_from is not None:
        return vacancy.salary_from >= minimum
    return True


async def launch_search(bot: Bot, app: "AppContext", chat_id: int, filters: Filters) -> None:
    existing = app.active.get(chat_id)
    if existing:
        if existing.paused and not existing.running:
            await resume_search(bot, app, existing)
            return
        if existing.running:
            await bot.send_message(chat_id, "🔎 Поиск уже идёт. Дождитесь следующей подборки.")
            return

    run = SearchRun(chat_id=chat_id, filters=filters)
    app.active[chat_id] = run
    try:
        await bot.send_message(
            chat_id,
            "🔎 <b>Ищу вакансии…</b>\n\n"
            f"Остановлюсь после {app.settings.batch_size} подходящих, чтобы не заваливать чат.",
            reply_markup=ui.stop_kb(),
        )
    except TelegramAPIError:
        log.exception("Не удалось отправить сообщение о старте поиска")
        app.active.pop(chat_id, None)
        return

    run.running = True
    run.task = asyncio.create_task(_search_loop(bot, app, run))


async def resume_search(bot: Bot, app: "AppContext", run: SearchRun) -> None:
    if run.running:
        await bot.send_message(run.chat_id, "🔎 Поиск уже идёт.")
        return
    run.paused = False
    run.stopped = False
    run.running = True
    run.task = asyncio.create_task(_search_loop(bot, app, run))


def stop_search(app: "AppContext", chat_id: int) -> SearchRun | None:
    run = app.active.pop(chat_id, None)
    if not run:
        return None
    run.stopped = True
    run.running = False
    run.paused = False
    task = run.task
    if task and not task.done():
        try:
            task.cancel()
        except RuntimeError:
            pass
    return run


async def _search_loop(bot: Bot, app: "AppContext", run: SearchRun) -> None:
    chat_id = run.chat_id
    try:
        while not run.stopped:
            try:
                page = await app.hh.search(run.filters, run.page)
            except HHBlockedError:
                await _safe_send(bot, chat_id, BLOCKED_TEXT)
                _finish(app, run)
                return
            except HHError as exc:
                log.warning("HH error: %s", exc)
                await _safe_send(bot, chat_id, ERROR_TEXT)
                _finish(app, run)
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Неожиданная ошибка поиска")
                await _safe_send(bot, chat_id, ERROR_TEXT)
                _finish(app, run)
                return

            run.last_page = page.last_page
            blacklist = app.db.blacklist_keywords(chat_id)

            for vacancy in page.vacancies:
                if run.stopped:
                    return
                if vacancy.id in run.seen:
                    continue
                run.seen.add(vacancy.id)

                if app.hh.is_excluded(vacancy):
                    continue
                if matches_blacklist(vacancy.name, blacklist):
                    continue
                if not _salary_matches(vacancy, run.filters.salary):
                    continue

                if app.settings.hh_token:
                    contacts = await app.hh.fetch_contacts(vacancy.id)
                    if contacts:
                        vacancy.contacts_text = contacts

                app.db.cache_vacancy(vacancy.to_dict())

                try:
                    await bot.send_message(
                        chat_id,
                        ui.format_card(vacancy),
                        reply_markup=ui.vacancy_kb(vacancy),
                    )
                except TelegramAPIError:
                    log.exception("Не удалось отправить вакансию %s", vacancy.id)
                    _finish(app, run)
                    return

                run.sent += 1

                if run.sent % app.settings.batch_size == 0:
                    run.paused = True
                    run.running = False
                    await _safe_send(
                        bot,
                        chat_id,
                        "⏸ <b>Остановился "
                        f"после {run.sent} вакансий</b>, чтобы не заваливать чат.\n\n"
                        "Продолжить поиск или остановиться?",
                        reply_markup=ui.batch_kb(app.settings.batch_size),
                    )
                    return

                await asyncio.sleep(app.settings.message_delay)

            limit_page = min(page.last_page, app.settings.max_pages - 1)
            if run.page >= limit_page:
                await _send_finished(bot, app, run, page.total, reached_limit=page.last_page > limit_page)
                _finish(app, run)
                return

            run.page += 1
            await asyncio.sleep(app.settings.page_delay)

    except asyncio.CancelledError:
        raise
    finally:
        run.running = False


async def _send_finished(
    bot: Bot,
    app: "AppContext",
    run: SearchRun,
    total: int,
    reached_limit: bool,
) -> None:
    if run.sent == 0:
        if total == 0:
            text = (
                "🔚 <b>Ничего не нашлось</b>\n\n"
                "По этим параметрам вакансий нет. Попробуйте изменить город, должность "
                "или убрать часть фильтров."
            )
        else:
            text = (
                "🔚 <b>Подходящих вакансий не нашлось</b>\n\n"
                "hh.ru что-то нашёл, но после фильтра по IT, зарплате и параметрам "
                "подходящих вакансий не осталось. Попробуйте изменить запрос."
            )
    elif reached_limit:
        text = (
            f"🔚 <b>Просмотрел первые {app.settings.max_pages} страниц</b>\n\n"
            f"Отправил {run.sent} подходящих вакансий. Чтобы не искать бесконечно, "
            "остановился. Уточните параметры, чтобы получить более точную подборку."
        )
    else:
        text = (
            "🔚 <b>Вакансии закончились</b>\n\n"
            f"Всего отправил {run.sent} подходящих вакансий по вашим параметрам."
        )
    await _safe_send(bot, run.chat_id, text, reply_markup=ui.exhausted_kb())


def _finish(app: "AppContext", run: SearchRun) -> None:
    run.running = False
    run.paused = False
    current = app.active.get(run.chat_id)
    if current is run:
        app.active.pop(run.chat_id, None)


async def _safe_send(bot: Bot, chat_id: int, text: str, reply_markup=None) -> None:
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
    except TelegramAPIError:
        log.exception("Не удалось отправить сообщение в чат %s", chat_id)
