from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import load_settings  # noqa: E402
from hh_client import HHClient  # noqa: E402
from models import Filters  # noqa: E402


async def main() -> None:
    settings = load_settings()
    client = HHClient(settings)
    try:
        print("Проверяю подсказки городов…")
        areas = await client.find_areas("Ростов")
        for area in areas[:4]:
            print("  ", area)

        filters = Filters(area_id="1", area_name="Москва", query="повар")
        print("\nИщу: Москва / повар…")
        page = await client.search(filters, 0)
        print(f"  всего: {page.total}, последняя страница: {page.last_page}, на странице: {len(page.vacancies)}")

        shown = 0
        for vacancy in page.vacancies:
            if client.is_excluded(vacancy):
                continue
            print(
                f"\n  {vacancy.name}\n"
                f"  {vacancy.company} · {vacancy.area}\n"
                f"  ЗП: {vacancy.salary_text}\n"
                f"  График: {vacancy.schedule_text} · Часы: {vacancy.hours_text}\n"
                f"  Опыт: {vacancy.experience_text}\n"
                f"  Контакты: {vacancy.contacts_text}\n"
                f"  {vacancy.url}"
            )
            shown += 1
            if shown >= 3:
                break
        if shown == 0:
            print("  Не нашлось не-IT вакансий на первой странице.")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
