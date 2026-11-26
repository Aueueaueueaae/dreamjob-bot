from __future__ import annotations

import html

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from hh_client import EXPERIENCE_LABELS, HOURS_LABELS, SCHEDULE_LABELS
from models import Filters, Vacancy

BTN_SEARCH = "🔍 Начать поиск"
BTN_FAVORITES = "⭐ Избранное"
BTN_EDIT = "⚙️ Изменить параметры"
BTN_STOP = "⏹ Остановить поиск"
BTN_BLACKLIST = "🚫 Чёрный список"
BTN_HELP = "❓ Помощь"

POPULAR_CITIES = [
    "Москва",
    "Санкт-Петербург",
    "Новосибирск",
    "Екатеринбург",
    "Казань",
    "Нижний Новгород",
    "Краснодар",
    "Ростов-на-Дону",
]

EXPERIENCE_CHOICES = [
    ("noExperience", "Без опыта"),
    ("between1And3", "1–3 года"),
    ("between3And6", "3–6 лет"),
    ("moreThan6", "Более 6 лет"),
    ("any", "Не важно"),
]

SCHEDULE_CHOICES = [
    ("FIVE_ON_TWO_OFF", "5/2"),
    ("TWO_ON_TWO_OFF", "2/2"),
    ("THREE_ON_THREE_OFF", "3/3"),
    ("FOUR_ON_TWO_OFF", "4/2"),
    ("SIX_ON_ONE_OFF", "6/1"),
    ("ONE_ON_THREE_OFF", "1/3"),
    ("FLEXIBLE", "Гибкий"),
    ("vahhta", "Вахта"),
    ("any", "Не важно"),
]

HOURS_CHOICES = [
    ("HOURS_8", "8 часов"),
    ("HOURS_12", "12 часов"),
    ("HOURS_24", "Сутки"),
    ("HOURS_6", "6 часов"),
    ("HOURS_4", "4 часа"),
    ("FLEXIBLE", "Гибкие"),
    ("any", "Не важно"),
]

START_TEXT = (
    "👋 <b>Привет!</b> Я помогу найти работу на hh.ru под ваши параметры.\n\n"
    "⚠️ Я <b>не ищу</b> вакансии в IT, а также курьеров, водителей, грузчиков, "
    "логистов, диспетчеров и похожие профессии — это жёсткие правила.\n\n"
    "Кнопки меню всегда внизу 👇"
)

CITY_TEXT = (
    "🏙 <b>Шаг 1 из 6.</b> В каком городе ищем работу?\n"
    "Напишите город сообщением или выберите из списка."
)

QUERY_TEXT = (
    "🔎 <b>Шаг 2 из 6.</b> Кого ищем?\n\n"
    "Напишите должность или ключевые слова — например: <i>продавец</i>, "
    "<i>повар</i>, <i>бухгалтер</i>, <i>менеджер по продажам</i>.\n"
    "Либо нажмите «Все профессии».\n\n"
    "⚠️ IT-профессии, курьеры, водители, грузчики, логисты и т.п. исключены из поиска."
)

SALARY_TEXT = (
    "💰 <b>Шаг 3 из 6.</b> Желаемый доход в месяц, ₽.\n\n"
    "Напишите число, например <code>80000</code>, или пропустите этот шаг."
)

EXPERIENCE_TEXT = "🎓 <b>Шаг 4 из 6.</b> Какой опыт работы вас устраивает?"

SCHEDULE_TEXT = "🗓 <b>Шаг 5 из 6.</b> Какой график работы вам подходит?"

HOURS_TEXT = "⏰ <b>Шаг 6 из 6.</b> Сколько часов в день вы готовы работать?"

HELP_TEXT = (
    "❓ <b>Как это работает</b>\n\n"
    "1. Нажмите «⚙️ Изменить параметры» (или /start) и ответьте на 6 вопросов: "
    "город, должность, доход, опыт, график и рабочие часы.\n"
    "2. Нажмите «🚀 Начать поиск». Бот ищет вакансии в фоне и присылает их по одной.\n"
    "3. Каждые 10 вакансий бот останавливается: можно продолжить или остановить поиск.\n"
    "4. Кнопка «⭐ В избранное» сохраняет вакансию. В разделе «⭐ Избранное» "
    "их можно листать стрелками и удалять.\n"
    "5. В разделе «🚫 Чёрный список» можно добавить свои слова или должности — "
    "вакансии с ними больше не будут показываться. Там же их можно удалить.\n\n"
    "⚠️ IT-вакансии, курьеры, водители, грузчики, логисты, диспетчеры, машинисты "
    "и похожие профессии не парсятся: ни по названию, ни по категории/роли на hh.ru.\n\n"
    "Команды:\n"
    "/start — заново собрать параметры\n"
    "/menu — главное меню\n"
    "/search — начать поиск с сохранёнными параметрами\n"
    "/favorites — избранные вакансии\n"
    "/blacklist — чёрный список\n"
    "/stop — остановить поиск\n"
    "/id — показать ваш Telegram ID\n"
    "/help — эта справка"
)

DISCLAIMER = (
    "⚠️ IT-вакансии, а также курьеры, водители, грузчики, логисты, диспетчеры, "
    "машинисты и похожие профессии отфильтровываются автоматически."
)


def esc(value: str) -> str:
    return html.escape(str(value or ""), quote=True)


def main_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_SEARCH), KeyboardButton(text=BTN_FAVORITES)],
            [KeyboardButton(text=BTN_EDIT), KeyboardButton(text=BTN_BLACKLIST)],
            [KeyboardButton(text=BTN_STOP), KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Пишите город или должность…",
    )


def cities_kb() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(POPULAR_CITIES), 2):
        row = [
            InlineKeyboardButton(text=city, callback_data=f"area:pop:{i + j}")
            for j, city in enumerate(POPULAR_CITIES[i : i + 2])
        ]
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🇷🇺 Вся Россия", callback_data="area:all")])
    rows.append([InlineKeyboardButton(text="✍️ Другой город", callback_data="area:text")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def area_candidates_kb(candidates: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_area_button_text(item),
                callback_data=f"area:cand:{i}",
            )
        ]
        for i, item in enumerate(candidates[:6])
    ]
    rows.append([InlineKeyboardButton(text="✍️ Ввести заново", callback_data="area:text")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _area_button_text(item: dict) -> str:
    name = str(item.get("name") or "")
    region = str(item.get("region") or "")
    if region and region.lower() not in {"россия", name.lower()}:
        return f"{name} · {region}"
    return name


def query_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Все профессии", callback_data="q:all")],
        ]
    )


def salary_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Не важно", callback_data="salary:skip")],
        ]
    )


def experience_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"exp:{value}")]
        for value, label in EXPERIENCE_CHOICES
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def schedule_kb() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(SCHEDULE_CHOICES), 2):
        rows.append(
            [
                InlineKeyboardButton(text=label, callback_data=f"sched:{value}")
                for value, label in SCHEDULE_CHOICES[i : i + 2]
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def hours_kb() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(HOURS_CHOICES), 2):
        rows.append(
            [
                InlineKeyboardButton(text=label, callback_data=f"hours:{value}")
                for value, label in HOURS_CHOICES[i : i + 2]
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def summary_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Начать поиск", callback_data="go:start")],
            [
                InlineKeyboardButton(text="🔄 Изменить параметры", callback_data="go:edit"),
                InlineKeyboardButton(text="⭐ Избранное", callback_data="fav:open"),
            ],
        ]
    )


def vacancy_kb(vacancy: Vacancy) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ В избранное",
                    callback_data=f"fav:add:{vacancy.id}",
                ),
                InlineKeyboardButton(text="🔗 Открыть", url=vacancy.url),
            ]
        ]
    )


def vacancy_added_kb(vacancy: Vacancy) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ В избранном", callback_data="fav:noop"),
                InlineKeyboardButton(text="🔗 Открыть", url=vacancy.url),
            ]
        ]
    )


def stop_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏹ Остановить поиск", callback_data="search:stop")],
        ]
    )


def batch_kb(batch_size: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"▶️ Продолжить (ещё {batch_size})",
                    callback_data="search:resume",
                ),
                InlineKeyboardButton(text="⏹ Остановить", callback_data="search:stop"),
            ],
            [InlineKeyboardButton(text="⭐ Избранное", callback_data="fav:open")],
        ]
    )


def exhausted_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Изменить параметры", callback_data="go:edit")],
            [InlineKeyboardButton(text="⭐ Избранное", callback_data="fav:open")],
        ]
    )


def favorites_kb(index: int, total: int, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️", callback_data="fav:prev"),
                InlineKeyboardButton(text=f"{index + 1} / {total}", callback_data="fav:noop"),
                InlineKeyboardButton(text="▶️", callback_data="fav:next"),
            ],
            [
                InlineKeyboardButton(text="🗑 Удалить", callback_data="fav:del"),
                InlineKeyboardButton(text="🔗 Открыть", url=url),
            ],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")],
        ]
    )


def menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 Начать поиск", callback_data="menu:search"),
                InlineKeyboardButton(text="⭐ Избранное", callback_data="fav:open"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Изменить параметры", callback_data="go:edit"),
                InlineKeyboardButton(text="🚫 Чёрный список", callback_data="bl:list:0"),
            ],
            [InlineKeyboardButton(text="⏹ Остановить", callback_data="search:stop")],
        ]
    )


BLACKLIST_PAGE_SIZE = 10

BLACKLIST_ADD_TEXT = (
    "➕ <b>Добавить в чёрный список</b>\n\n"
    "Напишите название должности или ключевое слово — например: "
    "<i>грузчик</i>, <i>продавец</i>, <i>менеджер</i>, <i>мойщик</i>.\n\n"
    "Если в названии вакансии встретится это слово, вакансия не будет показываться."
)


def blacklist_text(
    entries: list[dict],
    total: int,
    page: int,
    pages: int,
    notice: str | None = None,
) -> str:
    lines = ["🚫 <b>Чёрный список</b>", ""]
    if notice:
        lines.extend([notice, ""])

    if total == 0:
        lines.append("Список пуст. Добавьте слово или название должности.")
    else:
        lines.append(f"Слов: <b>{total}</b>. Совпадения по названию вакансии скрываются.")
        lines.append("")
        start = page * BLACKLIST_PAGE_SIZE
        for number, entry in enumerate(entries, start=start + 1):
            lines.append(f"{number}. {esc(entry['keyword'])}")
        lines.append("")
        lines.append("Нажмите «❌ слово», чтобы удалить его из списка.")
        if pages > 1:
            lines.append(f"Страница {page + 1} из {pages}.")

    lines.extend(
        [
            "",
            "⚠️ IT, курьеры, водители, грузчики, логисты, диспетчеры, машинисты "
            "и похожие профессии исключены всегда.",
        ]
    )
    return "\n".join(lines)


def blacklist_kb(entries: list[dict], page: int, pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for entry in entries:
        label = str(entry.get("keyword") or "")
        if len(label) > 45:
            label = label[:44] + "…"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"❌ {label}",
                    callback_data=f"bl:del:{entry['id']}:{page}",
                )
            ]
        )

    if pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=f"bl:page:{max(0, page - 1)}",
                ),
                InlineKeyboardButton(
                    text=f"{page + 1} / {pages}",
                    callback_data="bl:noop",
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=f"bl:page:{min(pages - 1, page + 1)}",
                ),
            ]
        )

    rows.append(
        [InlineKeyboardButton(text="➕ Добавить слово", callback_data=f"bl:add:{page}")]
    )
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def blacklist_add_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="bl:cancel")],
        ]
    )


def format_card(vacancy: Vacancy, favorite_index: int | None = None, favorite_total: int | None = None) -> str:
    lines = [
        f"🔹 <b>{esc(vacancy.name)}</b>",
        f"🏢 {esc(vacancy.company)}",
        f"📍 <b>Область:</b> {esc(vacancy.area)}",
        f"💰 <b>ЗП:</b> {esc(vacancy.salary_text)}",
        f"🗓 <b>График:</b> {esc(vacancy.schedule_text)}",
        f"⏰ <b>Рабочие часы:</b> {esc(vacancy.hours_text)}",
        f"🎓 <b>Опыт:</b> {esc(vacancy.experience_text)}",
    ]
    if vacancy.format_text and vacancy.format_text not in {"не указан"}:
        lines.append(f"🏠 <b>Формат:</b> {esc(vacancy.format_text)}")
    if vacancy.employment_text:
        lines.append(f"💼 <b>Занятость:</b> {esc(vacancy.employment_text)}")
    lines.append(f"📞 <b>Контакты:</b> {esc(vacancy.contacts_text)}")
    if vacancy.published_text:
        lines.append(f"🗓 <b>Опубликовано:</b> {esc(vacancy.published_text)}")
    lines.append(f'🔗 <a href="{esc(vacancy.url)}">Открыть вакансию на hh.ru</a>')
    if favorite_index is not None and favorite_total:
        lines.append(f"\n<i>⭐ Избранное · {favorite_index + 1} из {favorite_total}</i>")
    return "\n".join(lines)


def filters_text(filters: Filters) -> str:
    if filters.area_id == "113":
        city = "Вся Россия"
    else:
        city = filters.area_name
    query = filters.query or "все профессии"
    salary = f"от {filters.salary:,} ₽".replace(",", "\u202f") if filters.salary else "не важно"
    experience = EXPERIENCE_LABELS.get(filters.experience or "", "не важно")
    if filters.employment_form == "FLY_IN_FLY_OUT":
        schedule = "вахта"
    else:
        schedule = SCHEDULE_LABELS.get(filters.schedule or "", "не важно")
    hours = HOURS_LABELS.get(filters.hours or "", "не важно")
    return (
        f"🏙 <b>Город:</b> {esc(city)}\n"
        f"🔎 <b>Должность:</b> {esc(query)}\n"
        f"💰 <b>Желаемая ЗП:</b> {esc(salary)}\n"
        f"🎓 <b>Опыт:</b> {esc(experience)}\n"
        f"🗓 <b>График:</b> {esc(schedule)}\n"
        f"⏰ <b>Рабочие часы:</b> {esc(hours)}"
    )


def summary_text(filters: Filters) -> str:
    return (
        "✅ <b>Параметры поиска</b>\n\n"
        f"{filters_text(filters)}\n\n"
        f"{DISCLAIMER}"
    )


def menu_text(filters: Filters | None) -> str:
    if filters:
        return f"🏠 <b>Главное меню</b>\n\n{filters_text(filters)}"
    return "🏠 <b>Главное меню</b>\n\nПараметры ещё не заданы. Нажмите «⚙️ Изменить параметры»."
