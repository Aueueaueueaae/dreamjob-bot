from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import ui
from app import AppContext
from hh_client import excluded_reason, matches_blacklist
from models import Filters, Vacancy
from search import launch_search, resume_search, stop_search

log = logging.getLogger(__name__)
router = Router(name="job")


class Form(StatesGroup):
    city = State()
    area_choice = State()
    query = State()
    salary = State()
    experience = State()
    schedule = State()
    hours = State()
    confirm = State()
    ready = State()
    blacklist_input = State()


# ---------- вспомогательные функции ----------


async def _begin_survey(
    message: Message,
    state: FSMContext,
    app: AppContext,
    *,
    edit: bool = False,
) -> None:
    stop_search(app, message.chat.id)
    await state.clear()
    await state.set_state(Form.city)
    if edit:
        try:
            await message.edit_text(
                f"{ui.START_TEXT}\n\n{ui.CITY_TEXT}",
                reply_markup=ui.cities_kb(),
            )
            return
        except TelegramBadRequest:
            pass
    await message.answer(ui.START_TEXT, reply_markup=ui.main_reply_kb())
    await message.answer(ui.CITY_TEXT, reply_markup=ui.cities_kb())


async def _clear_blacklist_input(state: FSMContext) -> None:
    if await state.get_state() == Form.blacklist_input.state:
        await state.set_state(None)


def _filters_from_state(data: dict) -> Filters | None:
    payload = data.get("filters")
    if not isinstance(payload, dict) or not payload.get("area_id"):
        return None
    try:
        return Filters.from_dict(payload)
    except TypeError:
        return None


async def _current_filters(state: FSMContext, app: AppContext, user_id: int) -> Filters | None:
    current = await state.get_state()
    data = await state.get_data()
    if current in {Form.confirm.state, Form.ready.state}:
        found = _filters_from_state(data)
        if found:
            return found
    saved = app.db.load_filters(user_id)
    if saved:
        try:
            return Filters.from_dict(saved)
        except TypeError:
            pass
    return _filters_from_state(data)


def _parse_salary(text: str) -> int | None:
    cleaned = (
        (text or "")
        .lower()
        .replace("\u202f", "")
        .replace("\u00a0", "")
        .replace(" ", "")
        .replace("₽", "")
    )
    match = re.search(r"(\d+(?:[.,]\d+)?)(млн|million|к|k|тыс[а-я]*)?", cleaned)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", "."))
    except ValueError:
        return None
    suffix = match.group(2) or ""
    if suffix.startswith(("млн", "million")):
        value *= 1_000_000
    elif suffix.startswith(("к", "k", "тыс")) or value < 1000:
        value *= 1000
    if value <= 0 or value > 10_000_000:
        return None
    return int(round(value))


def _area_name(area: dict) -> str:
    if str(area.get("id")) == "113":
        return "Вся Россия"
    return str(area.get("name") or "").strip()


async def _select_area_callback(cb: CallbackQuery, state: FSMContext, area: dict) -> None:
    filters = Filters(
        area_id=str(area["id"]),
        area_name=_area_name(area),
    )
    await state.update_data(filters=filters.to_dict())
    await state.set_state(Form.query)
    if cb.message:
        try:
            await cb.message.edit_text(ui.QUERY_TEXT, reply_markup=ui.query_kb())
        except TelegramBadRequest:
            await cb.message.answer(ui.QUERY_TEXT, reply_markup=ui.query_kb())
    await cb.answer(f"Город: {filters.area_name}")


async def _ask_query(message: Message, state: FSMContext, filters: Filters) -> None:
    await state.update_data(filters=filters.to_dict())
    await state.set_state(Form.query)
    await message.answer(ui.QUERY_TEXT, reply_markup=ui.query_kb())


async def _to_salary_message(message: Message, state: FSMContext, filters: Filters) -> None:
    await state.update_data(filters=filters.to_dict())
    await state.set_state(Form.salary)
    await message.answer(ui.SALARY_TEXT, reply_markup=ui.salary_kb())


async def _to_salary_callback(cb: CallbackQuery, state: FSMContext, filters: Filters) -> None:
    await state.update_data(filters=filters.to_dict())
    await state.set_state(Form.salary)
    if cb.message:
        try:
            await cb.message.edit_text(ui.SALARY_TEXT, reply_markup=ui.salary_kb())
        except TelegramBadRequest:
            await cb.message.answer(ui.SALARY_TEXT, reply_markup=ui.salary_kb())
    await cb.answer()


async def _to_experience_callback(cb: CallbackQuery, state: FSMContext, filters: Filters) -> None:
    await state.update_data(filters=filters.to_dict())
    await state.set_state(Form.experience)
    if cb.message:
        try:
            await cb.message.edit_text(ui.EXPERIENCE_TEXT, reply_markup=ui.experience_kb())
        except TelegramBadRequest:
            await cb.message.answer(ui.EXPERIENCE_TEXT, reply_markup=ui.experience_kb())
    await cb.answer()


async def _to_schedule_callback(cb: CallbackQuery, state: FSMContext, filters: Filters) -> None:
    await state.update_data(filters=filters.to_dict())
    await state.set_state(Form.schedule)
    if cb.message:
        try:
            await cb.message.edit_text(ui.SCHEDULE_TEXT, reply_markup=ui.schedule_kb())
        except TelegramBadRequest:
            await cb.message.answer(ui.SCHEDULE_TEXT, reply_markup=ui.schedule_kb())
    await cb.answer()


async def _to_hours_callback(cb: CallbackQuery, state: FSMContext, filters: Filters) -> None:
    await state.update_data(filters=filters.to_dict())
    await state.set_state(Form.hours)
    if cb.message:
        try:
            await cb.message.edit_text(ui.HOURS_TEXT, reply_markup=ui.hours_kb())
        except TelegramBadRequest:
            await cb.message.answer(ui.HOURS_TEXT, reply_markup=ui.hours_kb())
    await cb.answer()


async def _to_summary_callback(cb: CallbackQuery, state: FSMContext, filters: Filters) -> None:
    await state.update_data(filters=filters.to_dict())
    await state.set_state(Form.confirm)
    if cb.message:
        try:
            await cb.message.edit_text(ui.summary_text(filters), reply_markup=ui.summary_kb())
        except TelegramBadRequest:
            await cb.message.answer(ui.summary_text(filters), reply_markup=ui.summary_kb())
    await cb.answer()


async def _send_favorites(message: Message, app: AppContext, user_id: int) -> None:
    ids = app.db.favorite_ids(user_id)
    if not ids:
        await message.answer(
            "⭐ <b>Избранное пусто</b>\n\n"
            "Добавляйте понравившиеся вакансии кнопкой «⭐ В избранное».",
            reply_markup=ui.menu_kb(),
        )
        return

    index = max(0, min(app.fav_index.get(user_id, 0), len(ids) - 1))
    app.fav_index[user_id] = index
    payload = app.db.get_vacancy(ids[index])
    if not payload:
        await message.answer(
            "⚠️ Не удалось загрузить вакансию из избранного. Попробуйте добавить её заново.",
            reply_markup=ui.menu_kb(),
        )
        return

    vacancy = Vacancy.from_dict(payload)
    await message.answer(
        ui.format_card(vacancy, index, len(ids)),
        reply_markup=ui.favorites_kb(index, len(ids), vacancy.url),
    )


async def _edit_favorites(cb: CallbackQuery, app: AppContext, user_id: int) -> None:
    ids = app.db.favorite_ids(user_id)
    if not ids or cb.message is None:
        return
    index = max(0, min(app.fav_index.get(user_id, 0), len(ids) - 1))
    app.fav_index[user_id] = index
    payload = app.db.get_vacancy(ids[index])
    if not payload:
        await cb.message.edit_text(
            "⚠️ Не удалось загрузить вакансию из избранного.",
            reply_markup=ui.menu_kb(),
        )
        return
    vacancy = Vacancy.from_dict(payload)
    try:
        await cb.message.edit_text(
            ui.format_card(vacancy, index, len(ids)),
            reply_markup=ui.favorites_kb(index, len(ids), vacancy.url),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            log.warning("Не удалось обновить избранное: %s", exc)


async def _send_blacklist(
    message: Message,
    app: AppContext,
    user_id: int,
    page: int = 0,
    notice: str | None = None,
) -> None:
    entries = app.db.blacklist_list(user_id)
    total = len(entries)
    pages = max(1, (total + ui.BLACKLIST_PAGE_SIZE - 1) // ui.BLACKLIST_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * ui.BLACKLIST_PAGE_SIZE
    visible = entries[start : start + ui.BLACKLIST_PAGE_SIZE]
    await message.answer(
        ui.blacklist_text(visible, total, page, pages, notice),
        reply_markup=ui.blacklist_kb(visible, page, pages),
    )


async def _edit_blacklist(
    cb: CallbackQuery,
    app: AppContext,
    user_id: int,
    page: int = 0,
    notice: str | None = None,
) -> None:
    if cb.message is None:
        return
    entries = app.db.blacklist_list(user_id)
    total = len(entries)
    pages = max(1, (total + ui.BLACKLIST_PAGE_SIZE - 1) // ui.BLACKLIST_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * ui.BLACKLIST_PAGE_SIZE
    visible = entries[start : start + ui.BLACKLIST_PAGE_SIZE]
    text = ui.blacklist_text(visible, total, page, pages, notice)
    markup = ui.blacklist_kb(visible, page, pages)
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        await cb.message.answer(text, reply_markup=markup)


async def _start_from_callback(
    cb: CallbackQuery,
    state: FSMContext,
    app: AppContext,
    bot: Bot,
) -> None:
    filters = await _current_filters(state, app, cb.from_user.id)
    if not filters:
        await cb.answer("Сначала задайте параметры поиска", show_alert=True)
        if cb.message:
            await _begin_survey(cb.message, state, app, edit=True)
        return

    app.db.save_filters(cb.from_user.id, filters.to_dict())
    await state.set_state(Form.ready)
    await cb.answer("Запускаю поиск")
    if cb.message:
        try:
            await cb.message.edit_text(
                "✅ Параметры сохранены.\n\n🔎 Запускаю поиск…",
                reply_markup=None,
            )
        except TelegramBadRequest:
            pass
    await bot.send_message(
        cb.message.chat.id if cb.message else cb.from_user.id,
        "Кнопки меню всегда внизу 👇",
        reply_markup=ui.main_reply_kb(),
    )
    await launch_search(
        bot,
        app,
        cb.message.chat.id if cb.message else cb.from_user.id,
        filters,
    )


async def _show_menu(message: Message, state: FSMContext, app: AppContext, user_id: int) -> None:
    filters = await _current_filters(state, app, user_id)
    await message.answer(ui.menu_text(filters), reply_markup=ui.menu_kb())


# ---------- команды ----------


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, app: AppContext) -> None:
    await _begin_survey(message, state, app)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, app: AppContext) -> None:
    await _clear_blacklist_input(state)
    await _show_menu(message, state, app, message.from_user.id)


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await _clear_blacklist_input(state)
    await message.answer(ui.HELP_TEXT, reply_markup=ui.main_reply_kb())


@router.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext, app: AppContext) -> None:
    await _clear_blacklist_input(state)
    run = stop_search(app, message.chat.id)
    if run:
        await message.answer("⏹ <b>Поиск остановлен.</b>")
    else:
        await message.answer("Активного поиска нет.")


@router.message(Command("favorites"))
async def cmd_favorites(message: Message, state: FSMContext, app: AppContext) -> None:
    await _clear_blacklist_input(state)
    await _send_favorites(message, app, message.from_user.id)


@router.message(Command("blacklist"))
async def cmd_blacklist(message: Message, state: FSMContext, app: AppContext) -> None:
    if await state.get_state() == Form.blacklist_input.state:
        await state.set_state(None)
    await _send_blacklist(message, app, message.from_user.id)


@router.message(Command("id"))
async def cmd_id(message: Message, state: FSMContext) -> None:
    await _clear_blacklist_input(state)
    await message.answer(
        f"Ваш Telegram ID: <code>{message.from_user.id}</code>\n\n"
        "Его можно вписать в <code>OWNER_ID</code> в .env, чтобы бот отвечал только вам."
    )


@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext, app: AppContext, bot: Bot) -> None:
    filters = await _current_filters(state, app, message.from_user.id)
    if not filters:
        await message.answer("Сначала задайте параметры поиска.")
        await _begin_survey(message, state, app)
        return
    app.db.save_filters(message.from_user.id, filters.to_dict())
    await state.set_state(Form.ready)
    await message.answer("🚀 Запускаю поиск…", reply_markup=ui.main_reply_kb())
    await launch_search(bot, app, message.chat.id, filters)


# ---------- постоянные кнопки ----------


@router.message(F.text == ui.BTN_SEARCH)
async def btn_search(message: Message, state: FSMContext, app: AppContext, bot: Bot) -> None:
    filters = await _current_filters(state, app, message.from_user.id)
    if not filters:
        await message.answer("Сначала задайте параметры поиска.")
        await _begin_survey(message, state, app)
        return
    app.db.save_filters(message.from_user.id, filters.to_dict())
    await state.set_state(Form.ready)
    await message.answer("🚀 Запускаю поиск…", reply_markup=ui.main_reply_kb())
    await launch_search(bot, app, message.chat.id, filters)


@router.message(F.text == ui.BTN_FAVORITES)
async def btn_favorites(message: Message, state: FSMContext, app: AppContext) -> None:
    await _clear_blacklist_input(state)
    await _send_favorites(message, app, message.from_user.id)


@router.message(F.text == ui.BTN_BLACKLIST)
async def btn_blacklist(message: Message, state: FSMContext, app: AppContext) -> None:
    if await state.get_state() == Form.blacklist_input.state:
        await state.set_state(None)
    await _send_blacklist(message, app, message.from_user.id)


@router.message(F.text == ui.BTN_EDIT)
async def btn_edit(message: Message, state: FSMContext, app: AppContext) -> None:
    await _begin_survey(message, state, app)


@router.message(F.text == ui.BTN_STOP)
async def btn_stop(message: Message, state: FSMContext, app: AppContext) -> None:
    await _clear_blacklist_input(state)
    run = stop_search(app, message.chat.id)
    if run:
        await message.answer("⏹ <b>Поиск остановлен.</b>")
    else:
        await message.answer("Активного поиска нет.")


@router.message(F.text == ui.BTN_HELP)
async def btn_help(message: Message, state: FSMContext) -> None:
    await _clear_blacklist_input(state)
    await message.answer(ui.HELP_TEXT, reply_markup=ui.main_reply_kb())


# ---------- шаг 1: город ----------


@router.callback_query(F.data.startswith("area:pop:"), StateFilter(Form.city))
async def area_popular(cb: CallbackQuery, state: FSMContext, app: AppContext) -> None:
    try:
        index = int((cb.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        await cb.answer("Не понял город", show_alert=True)
        return
    if not 0 <= index < len(ui.POPULAR_CITIES):
        await cb.answer("Не понял город", show_alert=True)
        return

    city = ui.POPULAR_CITIES[index]
    areas = await app.hh.find_areas(city)
    if not areas:
        await cb.answer("Не удалось найти город, напишите его сообщением", show_alert=True)
        return

    exact = next(
        (a for a in areas if str(a["name"]).strip().lower() == city.lower()),
        areas[0],
    )
    await _select_area_callback(cb, state, exact)


@router.callback_query(F.data == "area:all", StateFilter(Form.city))
async def area_all(cb: CallbackQuery, state: FSMContext) -> None:
    await _select_area_callback(cb, state, {"id": "113", "name": "Вся Россия"})


@router.callback_query(F.data == "area:text", StateFilter(Form.city, Form.area_choice))
async def area_text(cb: CallbackQuery) -> None:
    await cb.answer("Напишите город обычным сообщением", show_alert=False)


@router.callback_query(F.data.startswith("area:cand:"), StateFilter(Form.area_choice))
async def area_candidate(cb: CallbackQuery, state: FSMContext) -> None:
    try:
        index = int((cb.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        await cb.answer("Не понял город", show_alert=True)
        return
    data = await state.get_data()
    candidates = data.get("city_candidates") or []
    if not 0 <= index < len(candidates):
        await cb.answer("Вариант устарел, напишите город заново", show_alert=True)
        return
    await _select_area_callback(cb, state, candidates[index])


CITY_ALIASES = {
    "питер": "Санкт-Петербург",
    "спб": "Санкт-Петербург",
    "мск": "Москва",
    "екб": "Екатеринбург",
    "нск": "Новосибирск",
    "нн": "Нижний Новгород",
    "ростов": "Ростов-на-Дону",
    "ростов-на-дону": "Ростов-на-Дону",
}


@router.message(StateFilter(Form.city, Form.area_choice), F.text)
async def city_text(message: Message, state: FSMContext, app: AppContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Напишите название города (минимум 2 буквы).")
        return

    if text.lower() in {"россия", "вся россия", "рф"}:
        await _ask_query(message, state, Filters(area_id="113", area_name="Вся Россия"))
        return

    search_text = CITY_ALIASES.get(text.lower(), text)
    areas = await app.hh.find_areas(search_text)
    if not areas:
        await message.answer(
            "🤷 Не нашёл такой город. Попробуйте написать иначе — например, "
            "«Ростов-на-Дону» или «Нижний Новгород»."
        )
        return

    exact = next(
        (
            a
            for a in areas
            if str(a["name"]).strip().lower() in {search_text.lower(), text.lower()}
        ),
        None,
    )
    if exact:
        await _ask_query(
            message,
            state,
            Filters(area_id=str(exact["id"]), area_name=_area_name(exact)),
        )
        return

    if len(areas) == 1:
        only = areas[0]
        await _ask_query(
            message,
            state,
            Filters(area_id=str(only["id"]), area_name=_area_name(only)),
        )
        return

    await state.update_data(city_candidates=areas[:6])
    await state.set_state(Form.area_choice)
    await message.answer(
        "🔎 Нашёл несколько вариантов. Уточните, какой город нужен:",
        reply_markup=ui.area_candidates_kb(areas),
    )


# ---------- шаг 2: должность ----------


@router.callback_query(F.data == "q:all", StateFilter(Form.query))
async def query_all(cb: CallbackQuery, state: FSMContext) -> None:
    filters = _filters_from_state(await state.get_data())
    if not filters:
        await cb.answer("Город потерялся, начните заново: /start", show_alert=True)
        return
    filters.query = None
    await _to_salary_callback(cb, state, filters)


@router.message(StateFilter(Form.query), F.text)
async def query_text(message: Message, state: FSMContext, app: AppContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Напишите должность или ключевые слова (минимум 2 символа).")
        return

    if matches_blacklist(text, app.db.blacklist_keywords(message.from_user.id)):
        await message.answer(
            "⚠️ Это слово есть в вашем <b>чёрном списке</b>, поэтому поиск по нему "
            "ничего не покажет.\n\n"
            "Уберите слово в разделе «🚫 Чёрный список» (/blacklist) "
            "или введите другую должность."
        )
        return

    reason = excluded_reason(text)
    if reason == "forbidden":
        await message.answer(
            "🚫 <b>Эта профессия исключена</b>\n\n"
            "Я не ищу курьеров, водителей, грузчиков, логистов, диспетчеров, "
            "машинистов, трактористов, автослесарей и похожие профессии — "
            "это жёсткое правило.\n\n"
            "Напишите другую должность, например: продавец, повар, бухгалтер, "
            "медсестра, менеджер по продажам."
        )
        return
    if reason == "it":
        await message.answer(
            "🚫 <b>Это IT-профессия</b>\n\n"
            "Я не ищу вакансии, связанные с IT и программированием — это жёсткое правило. "
            "Напишите другую должность, например: продавец, повар, бухгалтер, "
            "медсестра, менеджер по продажам."
        )
        return

    filters = _filters_from_state(await state.get_data())
    if not filters:
        await message.answer("Город потерялся, начните заново: /start")
        return
    filters.query = text
    await _to_salary_message(message, state, filters)


# ---------- чёрный список: ввод слова ----------

BLACKLIST_LIMIT = 100


@router.message(StateFilter(Form.blacklist_input), F.text)
async def blacklist_input_text(message: Message, state: FSMContext, app: AppContext) -> None:
    raw = " ".join((message.text or "").strip().split())
    if len(raw) < 2:
        await message.answer(
            "Слишком коротко. Напишите хотя бы 2 символа или нажмите «Отмена».",
            reply_markup=ui.blacklist_add_kb(),
        )
        return
    if len(raw) > 100:
        await message.answer(
            "Слишком длинная фраза (максимум 100 символов). Сократите её.",
            reply_markup=ui.blacklist_add_kb(),
        )
        return

    user_id = message.from_user.id
    if app.db.blacklist_count(user_id) >= BLACKLIST_LIMIT:
        await state.set_state(None)
        await _send_blacklist(
            message,
            app,
            user_id,
            0,
            f"⚠️ Достигнут лимит: {BLACKLIST_LIMIT} слов. Удалите что-нибудь, чтобы добавить новое.",
        )
        return

    added, _ = app.db.blacklist_add(user_id, raw)
    await state.set_state(None)
    total = app.db.blacklist_count(user_id)
    page = max(0, (total - 1) // ui.BLACKLIST_PAGE_SIZE) if added else 0
    notice = (
        f"✅ Добавлено: <b>{ui.esc(raw)}</b>"
        if added
        else f"⚠️ «{ui.esc(raw)}» уже есть в чёрном списке."
    )
    await _send_blacklist(message, app, user_id, page, notice)


# ---------- шаг 3: зарплата ----------


@router.callback_query(F.data == "salary:skip", StateFilter(Form.salary))
async def salary_skip(cb: CallbackQuery, state: FSMContext) -> None:
    filters = _filters_from_state(await state.get_data())
    if not filters:
        await cb.answer("Параметры потерялись, начните заново: /start", show_alert=True)
        return
    filters.salary = None
    await _to_experience_callback(cb, state, filters)


@router.message(StateFilter(Form.salary), F.text)
async def salary_text(message: Message, state: FSMContext) -> None:
    value = _parse_salary(message.text or "")
    if not value:
        await message.answer(
            "Не понял сумму 🤔 Напишите число, например <code>80000</code>, "
            "или нажмите «Не важно».",
            reply_markup=ui.salary_kb(),
        )
        return

    filters = _filters_from_state(await state.get_data())
    if not filters:
        await message.answer("Параметры потерялись, начните заново: /start")
        return
    filters.salary = value
    await _to_experience_message(message, state, filters)


async def _to_experience_message(message: Message, state: FSMContext, filters: Filters) -> None:
    await state.update_data(filters=filters.to_dict())
    await state.set_state(Form.experience)
    await message.answer(ui.EXPERIENCE_TEXT, reply_markup=ui.experience_kb())


# ---------- шаг 4: опыт ----------


@router.callback_query(F.data.startswith("exp:"), StateFilter(Form.experience))
async def experience_choice(cb: CallbackQuery, state: FSMContext) -> None:
    value = (cb.data or "").split(":", 1)[1]
    filters = _filters_from_state(await state.get_data())
    if not filters:
        await cb.answer("Параметры потерялись, начните заново: /start", show_alert=True)
        return
    filters.experience = None if value == "any" else value
    await _to_schedule_callback(cb, state, filters)


# ---------- шаг 5: график ----------


@router.callback_query(F.data.startswith("sched:"), StateFilter(Form.schedule))
async def schedule_choice(cb: CallbackQuery, state: FSMContext) -> None:
    value = (cb.data or "").split(":", 1)[1]
    filters = _filters_from_state(await state.get_data())
    if not filters:
        await cb.answer("Параметры потерялись, начните заново: /start", show_alert=True)
        return

    if value == "vahhta":
        filters.schedule = None
        filters.employment_form = "FLY_IN_FLY_OUT"
    elif value == "any":
        filters.schedule = None
        filters.employment_form = None
    else:
        filters.schedule = value
        filters.employment_form = None
    await _to_hours_callback(cb, state, filters)


# ---------- шаг 6: рабочие часы ----------


@router.callback_query(F.data.startswith("hours:"), StateFilter(Form.hours))
async def hours_choice(cb: CallbackQuery, state: FSMContext) -> None:
    value = (cb.data or "").split(":", 1)[1]
    filters = _filters_from_state(await state.get_data())
    if not filters:
        await cb.answer("Параметры потерялись, начните заново: /start", show_alert=True)
        return
    filters.hours = None if value == "any" else value
    await _to_summary_callback(cb, state, filters)


# ---------- подтверждение ----------


@router.callback_query(F.data == "go:start", StateFilter(Form.confirm))
async def go_start(cb: CallbackQuery, state: FSMContext, app: AppContext, bot: Bot) -> None:
    await _start_from_callback(cb, state, app, bot)


@router.callback_query(F.data == "go:edit")
async def go_edit(cb: CallbackQuery, state: FSMContext, app: AppContext) -> None:
    await cb.answer()
    if cb.message:
        await _begin_survey(cb.message, state, app, edit=True)


@router.callback_query(F.data == "menu:home")
async def menu_home(cb: CallbackQuery, state: FSMContext, app: AppContext) -> None:
    filters = await _current_filters(state, app, cb.from_user.id)
    if cb.message:
        try:
            await cb.message.edit_text(ui.menu_text(filters), reply_markup=ui.menu_kb())
        except TelegramBadRequest:
            await cb.message.answer(ui.menu_text(filters), reply_markup=ui.menu_kb())
    await cb.answer()


@router.callback_query(F.data == "menu:search")
async def menu_search(cb: CallbackQuery, state: FSMContext, app: AppContext, bot: Bot) -> None:
    await _start_from_callback(cb, state, app, bot)


# ---------- поиск: пауза/продолжение ----------


@router.callback_query(F.data == "search:resume")
async def search_resume(cb: CallbackQuery, app: AppContext, bot: Bot) -> None:
    chat_id = cb.message.chat.id if cb.message else cb.from_user.id
    run = app.active.get(chat_id)
    if not run:
        await cb.answer("Поиск не активен. Начните заново: /start", show_alert=True)
        return
    if run.running:
        await cb.answer("Поиск уже идёт")
        return
    if cb.message:
        try:
            await cb.message.edit_text("▶️ <b>Продолжаю поиск…</b>", reply_markup=None)
        except TelegramBadRequest:
            pass
    await cb.answer("Продолжаю")
    await resume_search(bot, app, run)


@router.callback_query(F.data == "search:stop")
async def search_stop_cb(cb: CallbackQuery, app: AppContext) -> None:
    chat_id = cb.message.chat.id if cb.message else cb.from_user.id
    run = stop_search(app, chat_id)
    if cb.message:
        try:
            await cb.message.edit_text("⏹ <b>Поиск остановлен.</b>", reply_markup=None)
        except TelegramBadRequest:
            pass
    await cb.answer("Поиск остановлен" if run else "Активного поиска нет")


# ---------- избранное ----------


@router.callback_query(F.data == "fav:open")
async def fav_open(cb: CallbackQuery, app: AppContext) -> None:
    if cb.message:
        await _send_favorites(cb.message, app, cb.from_user.id)
    await cb.answer()


@router.callback_query(F.data == "fav:noop")
async def fav_noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(F.data.startswith("fav:add:"))
async def fav_add(cb: CallbackQuery, app: AppContext) -> None:
    vacancy_id = (cb.data or "").split(":", 2)[2]
    payload = app.db.get_vacancy(vacancy_id)
    if not payload:
        await cb.answer("Не удалось найти вакансию, попробуйте ещё раз", show_alert=True)
        return
    added = app.db.add_favorite(cb.from_user.id, vacancy_id)
    if cb.message:
        try:
            await cb.message.edit_reply_markup(
                reply_markup=ui.vacancy_added_kb(Vacancy.from_dict(payload))
            )
        except TelegramBadRequest:
            pass
    await cb.answer("Добавлено в избранное ⭐" if added else "Уже в избранном")


@router.callback_query(F.data == "fav:prev")
async def fav_prev(cb: CallbackQuery, app: AppContext) -> None:
    index = app.fav_index.get(cb.from_user.id, 0)
    if index <= 0:
        await cb.answer("Это первая вакансия")
        return
    app.fav_index[cb.from_user.id] = index - 1
    await cb.answer()
    await _edit_favorites(cb, app, cb.from_user.id)


@router.callback_query(F.data == "fav:next")
async def fav_next(cb: CallbackQuery, app: AppContext) -> None:
    ids = app.db.favorite_ids(cb.from_user.id)
    index = app.fav_index.get(cb.from_user.id, 0)
    if index >= len(ids) - 1:
        await cb.answer("Это последняя вакансия")
        return
    app.fav_index[cb.from_user.id] = index + 1
    await cb.answer()
    await _edit_favorites(cb, app, cb.from_user.id)


@router.callback_query(F.data == "fav:del")
async def fav_del(cb: CallbackQuery, app: AppContext) -> None:
    user_id = cb.from_user.id
    ids = app.db.favorite_ids(user_id)
    if not ids:
        await cb.answer("Избранное уже пусто")
        return
    index = max(0, min(app.fav_index.get(user_id, 0), len(ids) - 1))
    app.db.remove_favorite(user_id, ids[index])
    await cb.answer("Удалено из избранного")

    remaining = app.db.favorite_ids(user_id)
    if not remaining:
        app.fav_index[user_id] = 0
        if cb.message:
            await cb.message.edit_text(
                "⭐ <b>Избранное пусто</b>\n\n"
                "Добавляйте понравившиеся вакансии кнопкой «⭐ В избранное».",
                reply_markup=ui.menu_kb(),
            )
        return

    app.fav_index[user_id] = min(index, len(remaining) - 1)
    await _edit_favorites(cb, app, user_id)


@router.message(F.text.lower().contains("понрав"))
async def btn_liked_text(message: Message, app: AppContext) -> None:
    await _send_favorites(message, app, message.from_user.id)


@router.message(F.text.lower().contains("избран"))
async def btn_favorites_text(message: Message, app: AppContext) -> None:
    await _send_favorites(message, app, message.from_user.id)


# ---------- чёрный список ----------


@router.callback_query(F.data.startswith("bl:list:"))
async def bl_list(cb: CallbackQuery, app: AppContext) -> None:
    try:
        page = int((cb.data or "").split(":")[2])
    except (IndexError, ValueError):
        page = 0
    await _edit_blacklist(cb, app, cb.from_user.id, page)
    await cb.answer()


@router.callback_query(F.data.startswith("bl:page:"))
async def bl_page(cb: CallbackQuery, app: AppContext) -> None:
    try:
        page = int((cb.data or "").split(":")[2])
    except (IndexError, ValueError):
        page = 0
    await _edit_blacklist(cb, app, cb.from_user.id, page)
    await cb.answer()


@router.callback_query(F.data.startswith("bl:add"))
async def bl_add(cb: CallbackQuery, state: FSMContext, app: AppContext) -> None:
    user_id = cb.from_user.id
    if app.db.blacklist_count(user_id) >= BLACKLIST_LIMIT:
        await cb.answer(
            f"Достигнут лимит: {BLACKLIST_LIMIT} слов. Сначала удалите что-нибудь.",
            show_alert=True,
        )
        return
    parts = (cb.data or "").split(":")
    try:
        page = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        page = 0
    await state.set_state(Form.blacklist_input)
    await state.update_data(bl_page=page)
    if cb.message:
        try:
            await cb.message.edit_text(
                ui.BLACKLIST_ADD_TEXT,
                reply_markup=ui.blacklist_add_kb(),
            )
        except TelegramBadRequest:
            await cb.message.answer(
                ui.BLACKLIST_ADD_TEXT,
                reply_markup=ui.blacklist_add_kb(),
            )
    await cb.answer()


@router.callback_query(F.data == "bl:cancel")
async def bl_cancel(cb: CallbackQuery, state: FSMContext, app: AppContext) -> None:
    if await state.get_state() == Form.blacklist_input.state:
        await state.set_state(None)
    data = await state.get_data()
    try:
        page = int(data.get("bl_page") or 0)
    except (TypeError, ValueError):
        page = 0
    await _edit_blacklist(cb, app, cb.from_user.id, page)
    await cb.answer("Отменено")


@router.callback_query(F.data.startswith("bl:del:"))
async def bl_del(cb: CallbackQuery, app: AppContext) -> None:
    parts = (cb.data or "").split(":")
    if len(parts) < 3:
        await cb.answer("Не понял, что удалить", show_alert=True)
        return
    try:
        entry_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 0
    except ValueError:
        await cb.answer("Не понял, что удалить", show_alert=True)
        return

    user_id = cb.from_user.id
    keyword = next(
        (
            entry["keyword"]
            for entry in app.db.blacklist_list(user_id)
            if entry["id"] == entry_id
        ),
        None,
    )
    removed = app.db.blacklist_remove(user_id, entry_id)
    if removed and keyword:
        notice = f"✅ Удалено: <b>{ui.esc(keyword)}</b>"
        await cb.answer("Удалено")
    else:
        notice = "⚠️ Этого слова уже нет в списке."
        await cb.answer("Уже удалено")
    await _edit_blacklist(cb, app, user_id, page, notice)


@router.callback_query(F.data == "bl:noop")
async def bl_noop(cb: CallbackQuery) -> None:
    await cb.answer()


# ---------- устаревшие кнопки и свободный текст ----------


@router.callback_query()
async def stale_callback(cb: CallbackQuery) -> None:
    await cb.answer("Кнопка устарела. Начните заново: /start", show_alert=True)


@router.message()
async def fallback(message: Message) -> None:
    await message.answer(
        "Не понял 🤔 Используйте кнопки меню или команду /help.\n"
        "Чтобы заново задать параметры — /start."
    )
