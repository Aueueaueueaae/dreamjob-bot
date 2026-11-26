from __future__ import annotations

from dataclasses import dataclass, field

from config import Settings
from hh_client import HHClient
from models import SearchRun
from storage import Storage


@dataclass
class AppContext:
    settings: Settings
    db: Storage
    hh: HHClient
    active: dict[int, SearchRun] = field(default_factory=dict)
    fav_index: dict[int, int] = field(default_factory=dict)
