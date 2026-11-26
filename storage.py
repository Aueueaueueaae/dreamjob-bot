from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


class Storage:
    """Небольшое локальное хранилище: кэш вакансий, избранное и фильтры."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS vacancy_cache (
                    vacancy_id TEXT PRIMARY KEY,
                    payload    TEXT NOT NULL,
                    cached_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS favorites (
                    user_id    INTEGER NOT NULL,
                    vacancy_id TEXT NOT NULL,
                    added_at   TEXT NOT NULL,
                    PRIMARY KEY (user_id, vacancy_id)
                );

                CREATE TABLE IF NOT EXISTS user_filters (
                    user_id    INTEGER PRIMARY KEY,
                    payload    TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS blacklist (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    keyword    TEXT NOT NULL,
                    normalized TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (user_id, normalized)
                );

                CREATE INDEX IF NOT EXISTS idx_blacklist_user
                    ON blacklist (user_id);
                """
            )

    # ---------- кэш вакансий ----------

    def cache_vacancy(self, payload: dict) -> None:
        vacancy_id = str(payload["id"])
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO vacancy_cache (vacancy_id, payload, cached_at)
                VALUES (?, ?, ?)
                ON CONFLICT(vacancy_id) DO UPDATE SET
                    payload = excluded.payload,
                    cached_at = excluded.cached_at
                """,
                (vacancy_id, json.dumps(payload, ensure_ascii=False), now),
            )

    def get_vacancy(self, vacancy_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM vacancy_cache WHERE vacancy_id = ?",
                (str(vacancy_id),),
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["payload"])
        except json.JSONDecodeError:
            return None

    # ---------- избранное ----------

    def add_favorite(self, user_id: int, vacancy_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO favorites (user_id, vacancy_id, added_at)
                VALUES (?, ?, ?)
                """,
                (int(user_id), str(vacancy_id), now),
            )
            return cur.rowcount > 0

    def remove_favorite(self, user_id: int, vacancy_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM favorites WHERE user_id = ? AND vacancy_id = ?",
                (int(user_id), str(vacancy_id)),
            )
            return cur.rowcount > 0

    def is_favorite(self, user_id: int, vacancy_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM favorites WHERE user_id = ? AND vacancy_id = ?",
                (int(user_id), str(vacancy_id)),
            ).fetchone()
        return row is not None

    def favorite_ids(self, user_id: int) -> list[str]:
        """В порядке добавления: первая добавленная — первая в списке."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT vacancy_id FROM favorites
                WHERE user_id = ?
                ORDER BY added_at ASC, rowid ASC
                """,
                (int(user_id),),
            ).fetchall()
        return [row["vacancy_id"] for row in rows]

    def favorite_count(self, user_id: int) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS cnt FROM favorites WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    # ---------- фильтры ----------

    def save_filters(self, user_id: int, payload: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO user_filters (user_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (int(user_id), json.dumps(payload, ensure_ascii=False), now),
            )

    def load_filters(self, user_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM user_filters WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["payload"])
        except json.JSONDecodeError:
            return None

    # ---------- чёрный список пользователя ----------

    @staticmethod
    def _normalize_blacklist(keyword: str) -> str:
        return " ".join((keyword or "").lower().replace("ё", "е").split())

    def blacklist_add(self, user_id: int, keyword: str) -> tuple[bool, int | None]:
        clean = " ".join((keyword or "").strip().split())
        normalized = self._normalize_blacklist(clean)
        if not normalized:
            return False, None
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            try:
                cur = self._conn.execute(
                    """
                    INSERT INTO blacklist (user_id, keyword, normalized, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (int(user_id), clean, normalized, now),
                )
            except sqlite3.IntegrityError:
                return False, None
            return True, int(cur.lastrowid)

    def blacklist_remove(self, user_id: int, entry_id: int) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM blacklist WHERE user_id = ? AND id = ?",
                (int(user_id), int(entry_id)),
            )
            return cur.rowcount > 0

    def blacklist_list(self, user_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, keyword FROM blacklist
                WHERE user_id = ?
                ORDER BY id ASC
                """,
                (int(user_id),),
            ).fetchall()
        return [{"id": int(row["id"]), "keyword": str(row["keyword"])} for row in rows]

    def blacklist_keywords(self, user_id: int) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT normalized FROM blacklist WHERE user_id = ?",
                (int(user_id),),
            ).fetchall()
        return [str(row["normalized"]) for row in rows]

    def blacklist_count(self, user_id: int) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS cnt FROM blacklist WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()
