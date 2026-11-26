from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import AppContext  # noqa: E402
from config import load_settings  # noqa: E402
from hh_client import HHClient  # noqa: E402
from models import Filters  # noqa: E402
from search import launch_search, resume_search, stop_search  # noqa: E402
from storage import Storage  # noqa: E402


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str, object]] = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.messages.append((chat_id, text, reply_markup))
        print(f"[send] {text.splitlines()[0][:90]}")
        return None


async def main() -> None:
    settings = load_settings()
    settings = settings.__class__(
        bot_token="fake",
        hh_token=None,
        owner_id=None,
        db_path=Path(tempfile.gettempdir()) / "hh_bot_check.sqlite3",
        batch_size=3,
        message_delay=0.05,
        page_delay=0.05,
        max_pages=5,
        request_timeout=35,
    )
    db = Storage(settings.db_path)
    hh = HHClient(settings)
    app = AppContext(settings=settings, db=db, hh=hh)
    bot = FakeBot()

    filters = Filters(
        area_id="1",
        area_name="Москва",
        query="повар",
        experience="noExperience",
        schedule="FIVE_ON_TWO_OFF",
        hours="HOURS_8",
    )

    try:
        await launch_search(bot, app, 1, filters)
        run = app.active[1]
        for _ in range(200):
            if run.paused or not run.running:
                break
            await asyncio.sleep(0.1)
        print(f"\nПосле первой пачки: sent={run.sent}, paused={run.paused}, running={run.running}")
        assert run.paused and run.sent == 3, "ожидалась пауза после 3 вакансий"
        assert db.favorite_count(1) == 0

        await resume_search(bot, app, run)
        for _ in range(200):
            if run.paused or not run.running:
                break
            await asyncio.sleep(0.1)
        print(f"После второй пачки: sent={run.sent}, paused={run.paused}, running={run.running}")

        cached = next(
            (payload for payload in (db.get_vacancy(vid) for vid in run.seen) if payload),
            None,
        )
        print("Кэш вакансии:", "есть" if cached else "нет")

        if cached:
            print("Добавляю в избранное:", db.add_favorite(1, cached["id"]))
            print("Избранное:", db.favorite_ids(1))
            print("Удаляю:", db.remove_favorite(1, cached["id"]))
            print("Избранное после удаления:", db.favorite_ids(1))

        stop_search(app, 1)
        print("Остановлено, активных поисков:", len(app.active))

        # Проверка пользовательского чёрного списка в самом поиске
        db.blacklist_add(1, "повар")
        bot.messages.clear()
        await launch_search(bot, app, 1, filters)
        run2 = app.active[1]
        for _ in range(400):
            if run2.paused or not run2.running:
                break
            await asyncio.sleep(0.1)
        vacancy_messages = [
            text for _, text, _ in bot.messages if text.startswith("🔹")
        ]
        still_has = sum(
            1 for text in vacancy_messages if "повар" in text.lower()
        )
        print(
            f"С чёрным списком «повар»: отправлено {len(vacancy_messages)}, "
            f"с «повар» в названии — {still_has}"
        )
        db.blacklist_remove(1, db.blacklist_list(1)[0]["id"])
        stop_search(app, 1)
    finally:
        await hh.close()
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
