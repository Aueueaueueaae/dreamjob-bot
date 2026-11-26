from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import load_settings  # noqa: E402
from hh_client import HHClient, excluded_reason, matches_blacklist  # noqa: E402
from models import Filters  # noqa: E402


async def main() -> None:
    print("Проверка исключённых запросов:")
    for query in [
        "повар",
        "продавец",
        "менеджер",
        "python",
        "1С",
        "QA",
        "системный администратор",
        "курьер",
        "водитель",
        "водитель-экспедитор",
        "таксист",
        "дальнобойщик",
        "машинист",
        "тракторист",
        "автослесарь",
        "логист",
        "диспетчер",
        "менеджер по доставке",
        "грузчик",
        "погрузчик",
        "комплектовщик",
        "сборщик заказов",
        "кредитный специалист",
    ]:
        reason = excluded_reason(query)
        label = {"it": "IT", "forbidden": "ЗАПРЕЩЕНО"}.get(reason or "", "ok")
        print(f"  {query!r:35} -> {label}")

    print("\nПроверка чёрного списка:")
    for title, keywords in [
        ("Грузчик-комплектовщик", ["грузчик"]),
        ("Продавец-консультант", ["грузчик"]),
        ("Повар в столовую", ["повар", "официант"]),
        ("Водитель-курьер", ["повар"]),
    ]:
        print(f"  {title!r:35} {keywords} -> {'скрыть' if matches_blacklist(title, keywords) else 'показать'}")

    client = HHClient(load_settings())
    try:
        page = await client.search(Filters(area_id="1", area_name="Москва", query="менеджер"), 0)
        excluded = [v for v in page.vacancies if client.is_excluded(v)]
        allowed = [v for v in page.vacancies if not client.is_excluded(v)]
        print(f"\nМосква/менеджер: всего {page.total}, на странице {len(page.vacancies)}, "
              f"исключено {len(excluded)}, осталось {len(allowed)}")
        for vacancy in allowed[:5]:
            print(f"  OK {vacancy.name} | роли={vacancy.role_ids[:4]}")
        for vacancy in excluded[:5]:
            print(f"  EX {vacancy.name} | роли={vacancy.role_ids[:4]}")

        couriers = await client.search(Filters(area_id="1", area_name="Москва", query="курьер"), 0)
        courier_excluded = sum(1 for v in couriers.vacancies if client.is_excluded(v))
        print(f"\nМосква/курьер: всего {couriers.total}, на странице {len(couriers.vacancies)}, "
              f"исключено {courier_excluded}")

        filtered = await client.search(
            Filters(
                area_id="1",
                area_name="Москва",
                query="повар",
                experience="between1And3",
                schedule="FIVE_ON_TWO_OFF",
                hours="HOURS_8",
            ),
            0,
        )
        print(f"\nМосква/повар + опыт 1-3 + 5/2 + 8ч: всего {filtered.total}, "
              f"на странице {len(filtered.vacancies)}")
        for vacancy in filtered.vacancies[:3]:
            print(f"  {vacancy.name} | {vacancy.schedule_text} | {vacancy.hours_text}")

        hidden = sum(
            1 for v in filtered.vacancies if matches_blacklist(v.name, ["повар"])
        )
        print(f"Из них скрыл бы чёрный список по слову «повар»: {hidden}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
