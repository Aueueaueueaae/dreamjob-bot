from __future__ import annotations

import asyncio
import html as html_lib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

import aiohttp

from config import Settings
from models import Filters, Vacancy

log = logging.getLogger(__name__)

HH_BASE = "https://hh.ru"
SEARCH_URL = f"{HH_BASE}/search/vacancy"
AREAS_SUGGEST_URL = "https://api.hh.ru/suggests/areas"
API_VACANCY_URL = "https://api.hh.ru/vacancies/{id}"

STATE_RE = re.compile(
    r'<template[^>]*id="HH-Lux-InitialState"[^>]*>(.*?)</template>',
    re.DOTALL,
)

CURRENCY_SYMBOLS = {
    "RUR": "₽",
    "RUB": "₽",
    "USD": "$",
    "EUR": "€",
    "KZT": "₸",
    "BYN": "Br",
    "BYR": "Br",
    "UZS": "сум",
    "GEL": "₾",
    "AZN": "₼",
    "KGS": "сом",
    "AMD": "֏",
}

MODE_SUFFIX = {
    "MONTH": "",
    "HOUR": "в час",
    "SHIFT": "за смену",
    "DAY": "в день",
    "WEEK": "в неделю",
    "FLY_IN_FLY_OUT": "за вахту",
}

EXPERIENCE_LABELS = {
    "noExperience": "без опыта",
    "between1And3": "1–3 года",
    "between3And6": "3–6 лет",
    "moreThan6": "более 6 лет",
}

SCHEDULE_LABELS = {
    "FIVE_ON_TWO_OFF": "5/2",
    "TWO_ON_TWO_OFF": "2/2",
    "THREE_ON_THREE_OFF": "3/3",
    "FOUR_ON_TWO_OFF": "4/2",
    "FOUR_ON_THREE_OFF": "4/3",
    "FOUR_ON_FOUR_OFF": "4/4",
    "SIX_ON_ONE_OFF": "6/1",
    "THREE_ON_TWO_OFF": "3/2",
    "TWO_ON_ONE_OFF": "2/1",
    "ONE_ON_THREE_OFF": "1/3",
    "ONE_ON_TWO_OFF": "1/2",
    "WEEKEND": "по выходным",
    "FLEXIBLE": "гибкий",
    "OTHER": "другой",
}

HOURS_LABELS = {
    "HOURS_2": "2 часа",
    "HOURS_3": "3 часа",
    "HOURS_4": "4 часа",
    "HOURS_5": "5 часов",
    "HOURS_6": "6 часов",
    "HOURS_7": "7 часов",
    "HOURS_8": "8 часов",
    "HOURS_9": "9 часов",
    "HOURS_10": "10 часов",
    "HOURS_11": "11 часов",
    "HOURS_12": "12 часов",
    "HOURS_24": "сутки",
    "FLEXIBLE": "гибкие",
    "OTHER": "другие",
}

WORK_FORMAT_LABELS = {
    "ON_SITE": "в офисе",
    "REMOTE": "удалённо",
    "HYBRID": "гибрид",
    "FIELD_WORK": "разъездная",
}

EMPLOYMENT_LABELS = {
    "FULL": "полная занятость",
    "PART": "частичная занятость",
    "PROJECT": "проектная работа",
    "FLY_IN_FLY_OUT": "вахта",
    "PROBATION": "стажировка",
    "VOLUNTEER": "волонтёрство",
}

# Роли из категории «Информационные технологии» на случай, если дерево ролей
# не удалось прочитать со страницы. Дополняется динамически при каждом поиске.
FALLBACK_IT_ROLE_IDS = {
    "156", "160", "10", "12", "150", "25", "165", "34", "36", "73",
    "155", "96", "164", "104", "157", "107", "112", "113", "148", "114",
    "116", "121", "124", "125", "126",
}

IT_TITLE_SUBSTRINGS = (
    "программист",
    "программирован",
    "разработчик",
    "developer",
    "software engineer",
    "frontend",
    "backend",
    "fullstack",
    "full-stack",
    "devops",
    "qa-инженер",
    "qa engineer",
    "тестировщик",
    "сисадмин",
    "системный администратор",
    "sysadmin",
    "сетевой инженер",
    "системный инженер",
    "системный аналитик",
    "аналитик данных",
    "bi-аналитик",
    "продуктовый аналитик",
    "data scientist",
    "дата-сайентист",
    "machine learning",
    "ml-инженер",
    "mlops",
    "data engineer",
    "дата-инженер",
    "python",
    "django",
    "fastapi",
    "javascript",
    "typescript",
    "golang",
    "битрикс",
    "bitrix",
    "верстальщик",
    "веб-разработчик",
    "гейм-дизайнер",
    "технический писатель",
    "информационная безопасность",
    "информационной безопасности",
    "информационные технологии",
    "кибербезопасн",
    "архитектор по",
    "1с-разработчик",
    "1c-разработчик",
)

IT_TITLE_RE = re.compile(
    r"(?<![а-яёa-z])(it|ит|qa|sre|cto|cio|java|php|sql|1с|1c|c\+\+|c#|\.net)(?![а-яёa-z])",
    re.IGNORECASE,
)

IT_QUERY_SUBSTRINGS = IT_TITLE_SUBSTRINGS + (
    "java ",
    "php",
    "sql",
    "1с",
    "1c",
    "айти",
    "it-",
    "android-разработчик",
    "ios-разработчик",
    "kotlin",
    "swift",
    "react native",
)

# Профессии, которые бот не ищет по просьбе владельца.
FORBIDDEN_ROLE_IDS = {
    "21",  # Водитель, экспедитор
    "58",  # Курьер, Почтальон
}

FORBIDDEN_TITLE_STEMS = (
    # курьеры и доставка
    "курьер",
    "доставщик",
    "развозчик",
    "посыльн",
    "почтальон",
    # водители и транспорт
    "водител",
    "шофер",
    "шофёр",
    "экспедит",
    "таксист",
    "дальнобойщик",
    "машинист",
    "тракторист",
    "автослесар",
    "логист",
    "диспетчер",
    "менеджер по доставк",
    "менеджер доставк",
    # грузчики и погрузка
    "грузчик",
    "погруз",
    "разгруз",
    "комплектовщик",
    "сборщик заказ",
    "сборщик онлайн",
)


class HHError(Exception):
    """Базовая ошибка работы с hh.ru."""


class HHBlockedError(HHError):
    """hh.ru показал капчу/антибот или запретил доступ."""


class HHParseError(HHError):
    """Не удалось разобрать страницу hh.ru."""


@dataclass
class VacancyPage:
    vacancies: list[Vacancy]
    page: int
    total: int
    last_page: int


def normalize_text(value: str) -> str:
    """Приводит текст к виду для регистронезависимого поиска подстрок."""
    return " ".join((value or "").lower().replace("ё", "е").split())


def looks_like_it_query(text: str) -> bool:
    """Грубая проверка: пользователь ищет именно IT-профессию."""
    low = normalize_text(text)
    if not low:
        return False
    if any(token in low for token in IT_QUERY_SUBSTRINGS):
        return True
    return bool(IT_TITLE_RE.search(low))


def looks_like_it_title(text: str) -> bool:
    low = normalize_text(text)
    if any(token in low for token in IT_TITLE_SUBSTRINGS):
        return True
    return bool(IT_TITLE_RE.search(low))


def looks_like_forbidden_title(text: str) -> bool:
    """Курьеры, водители, грузчики, логисты и близкие к ним профессии."""
    low = normalize_text(text)
    return any(stem in low for stem in FORBIDDEN_TITLE_STEMS)


def excluded_reason(text: str) -> str | None:
    """Возвращает 'it' / 'forbidden', если запрос относится к исключённым."""
    if looks_like_it_query(text):
        return "it"
    if looks_like_forbidden_title(text):
        return "forbidden"
    return None


def matches_blacklist(title: str, keywords: list[str]) -> bool:
    """Проверяет название вакансии по словам пользовательского чёрного списка."""
    low = normalize_text(title)
    return any(keyword and keyword in low for keyword in keywords)


def _collect_strings(value, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_strings(item, out)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_strings(item, out)


def _collect_ints(value, out: set[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        out.add(str(value))
    elif isinstance(value, str):
        if value.isdigit():
            out.add(value)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_ints(item, out)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_ints(item, out)


def _labels(values: list[str], mapping: dict[str, str], max_items: int = 3) -> str:
    labels: list[str] = []
    for value in values:
        label = mapping.get(value)
        if label and label not in labels:
            labels.append(label)
    if len(labels) > max_items:
        return "разные варианты"
    return ", ".join(labels)


def _money(value: int) -> str:
    return f"{value:,}".replace(",", "\u202f")


def format_salary(compensation: dict | None) -> tuple[str, int | None, int | None, str | None]:
    if not compensation or compensation.get("noCompensation"):
        return "не указана", None, None, None

    frm = compensation.get("from")
    to = compensation.get("to")
    if frm is None and to is None:
        frm = compensation.get("perModeFrom")
        to = compensation.get("perModeTo")
    currency = compensation.get("currencyCode") or compensation.get("currency")
    symbol = CURRENCY_SYMBOLS.get(str(currency or "").upper(), currency or "₽")

    if frm is None and to is None:
        return "не указана", None, None, currency

    if frm is not None and to is not None:
        amount = f"{_money(int(frm))} – {_money(int(to))} {symbol}"
    elif frm is not None:
        amount = f"от {_money(int(frm))} {symbol}"
    else:
        amount = f"до {_money(int(to))} {symbol}"

    mode = compensation.get("mode")
    mode_suffix = MODE_SUFFIX.get(mode or "", "")
    gross = compensation.get("gross")
    if gross is True:
        gross_note = "до вычета налогов"
    elif gross is False:
        gross_note = "на руки"
    else:
        gross_note = ""

    extras = [part for part in (mode_suffix, gross_note) if part]
    text = amount + (f" ({', '.join(extras)})" if extras else "")
    return text, (int(frm) if frm is not None else None), (int(to) if to is not None else None), currency


def _parse_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return ""


def _collect_contact_strings(value, out: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"name", "email", "phone", "formatted", "number"} and isinstance(item, str):
                out.append(item)
            elif isinstance(item, (dict, list)):
                _collect_contact_strings(item, out)
    elif isinstance(value, list):
        for item in value:
            _collect_contact_strings(item, out)


def contacts_from_card(card: dict) -> str:
    info = card.get("contactInfo")
    if isinstance(info, dict) and info.get("contactsHidden"):
        return "скрыты на hh.ru (видны после входа)"
    if info:
        parts: list[str] = []
        _collect_contact_strings(info, parts)
        cleaned = []
        for part in parts:
            part = part.strip()
            if part and part not in cleaned:
                cleaned.append(part)
        if cleaned:
            return ", ".join(cleaned[:4])
    if card.get("@showContact"):
        return "указаны на странице вакансии"
    return "не указаны"


class HHClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._hh_token = settings.hh_token
        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()
        self._it_roles: set[str] = set(FALLBACK_IT_ROLE_IDS)

        self._browser_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        self._api_headers = {
            "User-Agent": "HHJobBot/1.0 (telegram job search bot)",
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.9",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        async with self._session_lock:
            if self._session is None or self._session.closed:
                timeout = aiohttp.ClientTimeout(total=self._settings.request_timeout)
                self._session = aiohttp.ClientSession(
                    timeout=timeout,
                    headers=self._browser_headers,
                    cookie_jar=aiohttp.CookieJar(unsafe=True),
                )
            return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ---------- города ----------

    async def find_areas(self, query: str) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []
        session = await self._get_session()
        try:
            async with session.get(
                AREAS_SUGGEST_URL,
                params={"text": query},
                headers=self._api_headers,
            ) as response:
                if response.status >= 400:
                    log.warning("hh areas suggest HTTP %s", response.status)
                    return []
                data = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("areas suggest failed: %s", exc)
            return []

        result: list[dict] = []
        seen: set[str] = set()
        for item in data.get("items") or []:
            area_id = str(item.get("id") or "")
            name = str(item.get("text") or "")
            if not area_id or not name or area_id in seen:
                continue
            seen.add(area_id)
            parent = item.get("parent") or {}
            region = str(parent.get("text") or "")
            result.append({"id": area_id, "name": name, "region": region})
        return result

    # ---------- поиск ----------

    def _search_params(self, filters: Filters, page: int) -> dict[str, object]:
        params: dict[str, object] = {
            "area": filters.area_id,
            "page": page,
            "items_on_page": 50,
            "order_by": "publication_time",
            "no_magic": "true",
            "host": "hh.ru",
            "locale": "RU",
        }
        if filters.query:
            params["text"] = filters.query
        if filters.experience:
            params["experience"] = filters.experience
        if filters.schedule:
            params["work_schedule_by_days"] = filters.schedule
        if filters.hours:
            params["working_hours"] = filters.hours
        if filters.employment_form:
            params["employment_form"] = filters.employment_form
        return params

    async def search(self, filters: Filters, page: int = 0) -> VacancyPage:
        session = await self._get_session()
        params = self._search_params(filters, page)
        url = f"{SEARCH_URL}?{urlencode(params)}"

        try:
            async with session.get(url, headers=self._browser_headers) as response:
                body = await response.text(errors="replace")
                status = response.status
                final_url = str(response.url)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise HHError(f"Не удалось подключиться к hh.ru: {exc}") from exc

        if status == 403:
            raise HHBlockedError("hh.ru вернул 403")
        if status >= 400:
            raise HHError(f"hh.ru вернул HTTP {status}")

        if "/captcha" in final_url or "showcaptcha" in final_url.lower():
            raise HHBlockedError("hh.ru требует капчу")

        state = self._extract_state(body)
        search_result = state.get("vacancySearchResult")
        if not isinstance(search_result, dict):
            if "captcha" in body.lower():
                raise HHBlockedError("hh.ru требует капчу")
            raise HHParseError("В странице hh.ru нет блока vacancySearchResult")

        self._refresh_it_roles(state)

        vacancies = [
            self._vacancy_from_card(card)
            for card in (search_result.get("vacancies") or [])
            if isinstance(card, dict) and card.get("vacancyId")
        ]
        paging = search_result.get("paging") or {}
        last_page = paging.get("lastPage") or {}
        try:
            last_page_num = int(last_page.get("page", page))
        except (TypeError, ValueError):
            last_page_num = page
        try:
            total = int(search_result.get("totalResults") or 0)
        except (TypeError, ValueError):
            total = 0

        return VacancyPage(
            vacancies=vacancies,
            page=page,
            total=total,
            last_page=max(last_page_num, page),
        )

    def _extract_state(self, body: str) -> dict:
        match = STATE_RE.search(body)
        if not match:
            lowered = body.lower()
            if "/captcha" in lowered or "showcaptcha" in lowered or "antirobot" in lowered:
                raise HHBlockedError("hh.ru требует капчу")
            raise HHParseError("Не найден HH-Lux-InitialState")
        raw = html_lib.unescape(match.group(1))
        try:
            state = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HHParseError(f"Некорректный JSON со страницы hh.ru: {exc}") from exc
        if not isinstance(state, dict):
            raise HHParseError("Неожиданный формат состояния hh.ru")
        return state

    def _refresh_it_roles(self, state: dict) -> None:
        tree = state.get("professionalRoleTree") or {}
        items = tree.get("items") if isinstance(tree, dict) else None
        if not isinstance(items, list):
            return
        for category in items:
            if not isinstance(category, dict):
                continue
            name = str(category.get("text") or "").lower()
            if "информационн" not in name:
                continue
            for role in category.get("items") or []:
                if isinstance(role, dict) and role.get("id") is not None:
                    self._it_roles.add(str(role["id"]))
            break

    def _vacancy_from_card(self, card: dict) -> Vacancy:
        vacancy_id = str(card.get("vacancyId") or "")
        compensation = card.get("compensation") if isinstance(card.get("compensation"), dict) else {}
        salary_text, salary_from, salary_to, currency = format_salary(compensation)

        schedule_values: list[str] = []
        _collect_strings(card.get("workScheduleByDays"), schedule_values)
        schedule_text = _labels(schedule_values, SCHEDULE_LABELS)

        hours_values: list[str] = []
        _collect_strings(card.get("workingHours"), hours_values)
        hours_text = _labels(hours_values, HOURS_LABELS)

        format_values: list[str] = []
        _collect_strings(card.get("workFormats"), format_values)
        format_text = _labels(format_values, WORK_FORMAT_LABELS)

        employment_form = str(card.get("employmentForm") or "")
        employment_text = EMPLOYMENT_LABELS.get(employment_form, "")
        if employment_form == "FLY_IN_FLY_OUT":
            schedule_text = "вахта"

        role_ids: set[str] = set()
        _collect_ints(card.get("professionalRoleIds"), role_ids)

        company = card.get("company") if isinstance(card.get("company"), dict) else {}
        company_name = str(
            company.get("visibleName") or company.get("name") or "Компания не указана"
        ).strip()

        area = card.get("area") if isinstance(card.get("area"), dict) else {}
        area_name = str(area.get("name") or "не указана").strip()

        links = card.get("links") if isinstance(card.get("links"), dict) else {}
        url = str(links.get("desktop") or f"{HH_BASE}/vacancy/{vacancy_id}")

        published = card.get("publicationTime")
        published_raw = ""
        if isinstance(published, dict):
            published_raw = str(published.get("$") or "")
        elif isinstance(published, str):
            published_raw = published

        return Vacancy(
            id=vacancy_id,
            name=str(card.get("name") or "Без названия").strip(),
            company=company_name,
            area=area_name,
            salary_text=salary_text,
            schedule_text=schedule_text or "не указан",
            hours_text=hours_text or "не указаны",
            experience_text=EXPERIENCE_LABELS.get(str(card.get("workExperience") or ""), "не указан"),
            format_text=format_text or "не указан",
            employment_text=employment_text,
            contacts_text=contacts_from_card(card),
            url=url,
            published_text=_parse_date(published_raw),
            role_ids=sorted(role_ids),
            salary_from=salary_from,
            salary_to=salary_to,
            currency=currency,
        )

    def is_excluded(self, vacancy: Vacancy) -> bool:
        roles = set(vacancy.role_ids)
        if roles and (roles & self._it_roles or roles & FORBIDDEN_ROLE_IDS):
            return True
        return looks_like_it_title(vacancy.name) or looks_like_forbidden_title(vacancy.name)

    # ---------- контакты (только при наличии HH_TOKEN) ----------

    async def fetch_contacts(self, vacancy_id: str) -> str | None:
        if not self._hh_token:
            return None
        session = await self._get_session()
        headers = dict(self._api_headers)
        headers["Authorization"] = f"Bearer {self._hh_token}"
        try:
            async with session.get(
                API_VACANCY_URL.format(id=vacancy_id),
                headers=headers,
            ) as response:
                if response.status >= 400:
                    return None
                data = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None

        contacts = data.get("contacts") or []
        parts: list[str] = []
        for contact in contacts:
            if not isinstance(contact, dict):
                continue
            name = str(contact.get("name") or "").strip()
            email = str(contact.get("email") or "").strip()
            phones: list[str] = []
            for phone in contact.get("phones") or []:
                if isinstance(phone, dict):
                    value = phone.get("formatted") or phone.get("number")
                    if value:
                        phones.append(str(value).strip())
                elif isinstance(phone, str):
                    phones.append(phone.strip())
            chunk = name
            if phones:
                chunk = f"{chunk}: {', '.join(phones)}" if chunk else ", ".join(phones)
            if email:
                chunk = f"{chunk}, {email}" if chunk else email
            chunk = chunk.strip(" ,")
            if chunk and chunk not in parts:
                parts.append(chunk)
        return "; ".join(parts) if parts else None
