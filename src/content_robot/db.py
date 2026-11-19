"""Lưu trữ SQLite: bài gốc, biến thể theo kênh, chỉ số tương tác, nhật ký."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wp_id INTEGER UNIQUE NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TEXT,
    categories TEXT,
    excerpt TEXT,
    content_text TEXT,
    headings TEXT,
    image_url TEXT,
    image_alt TEXT,
    products TEXT,
    analysis TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    error TEXT,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT,
    body TEXT NOT NULL,
    link TEXT,
    alt_text TEXT,
    overlay TEXT,
    board TEXT,
    image_path TEXT,
    compliance_status TEXT,
    compliance_issues TEXT,
    ai_provider TEXT,
    ai_model TEXT,
    feedback TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_by TEXT,
    approved_at TEXT,
    scheduled_at TEXT,
    published_at TEXT,
    remote_id TEXT,
    remote_url TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    UNIQUE(article_id, channel)
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    variant_id INTEGER NOT NULL REFERENCES variants(id),
    collected_at TEXT NOT NULL,
    impressions INTEGER, reactions INTEGER, comments INTEGER,
    shares INTEGER, saves INTEGER, clicks INTEGER,
    simulated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    entity TEXT,
    entity_id INTEGER,
    message TEXT NOT NULL
);
"""

JSON_FIELDS = {"categories", "headings", "products", "analysis", "compliance_issues", "trace"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)
            cols = {r[1] for r in c.execute("PRAGMA table_info(articles)").fetchall()}
            if "trace" not in cols:
                c.execute("ALTER TABLE articles ADD COLUMN trace TEXT")

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    @staticmethod
    def _encode(values: dict[str, Any]) -> dict[str, Any]:
        return {k: (json.dumps(v, ensure_ascii=False) if k in JSON_FIELDS and v is not None else v) for k, v in values.items()}

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        d = dict(row)
        for k in JSON_FIELDS & d.keys():
            if d[k]:
                d[k] = json.loads(d[k])
        return d

    def insert(self, table: str, values: dict[str, Any]) -> int:
        v = self._encode(values)
        cols = ", ".join(v)
        qs = ", ".join("?" for _ in v)
        with self.conn() as c:
            cur = c.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", list(v.values()))
            return int(cur.lastrowid)

    def update(self, table: str, row_id: int, values: dict[str, Any]) -> None:
        v = self._encode(values)
        sets = ", ".join(f"{k} = ?" for k in v)
        with self.conn() as c:
            c.execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*v.values(), row_id])

    def one(self, sql: str, args: tuple = ()) -> dict[str, Any] | None:
        with self.conn() as c:
            return self._decode(c.execute(sql, args).fetchone())

    def all(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with self.conn() as c:
            return [self._decode(r) for r in c.execute(sql, args).fetchall()]  # type: ignore[misc]

    def log(self, message: str, level: str = "info", entity: str | None = None, entity_id: int | None = None) -> None:
        self.insert("events", {"ts": now_iso(), "level": level, "entity": entity, "entity_id": entity_id, "message": message})
