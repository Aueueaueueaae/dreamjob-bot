from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Filters:
    """Параметры поиска, которые собрал бот."""

    area_id: str
    area_name: str
    query: str | None = None
    salary: int | None = None
    experience: str | None = None
    schedule: str | None = None
    hours: str | None = None
    employment_form: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Filters":
        allowed = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class Vacancy:
    """Вакансия, уже подготовленная для показа в Telegram."""

    id: str
    name: str
    company: str
    area: str
    salary_text: str
    schedule_text: str
    hours_text: str
    experience_text: str
    format_text: str
    employment_text: str
    contacts_text: str
    url: str
    published_text: str
    role_ids: list[str] = field(default_factory=list)
    salary_from: int | None = None
    salary_to: int | None = None
    currency: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Vacancy":
        allowed = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class SearchRun:
    """Состояние одного активного поиска."""

    chat_id: int
    filters: Filters
    page: int = 0
    seen: set[str] = field(default_factory=set)
    sent: int = 0
    last_page: int | None = None
    paused: bool = False
    running: bool = False
    stopped: bool = False
    task: object | None = None
