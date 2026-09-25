"""store.py — SQLite persistence for runtime configuration overrides."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Any

from src.config.constants import DEFAULT_DB_PATH

_lock = threading.RLock()


def get_config_db_path(db_path: str | None = None) -> str:
    if db_path:
        return db_path
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, DEFAULT_DB_PATH)


def init_config_table(db_path: str | None = None) -> None:
    path = get_config_db_path(db_path)
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with _lock, sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS runtime_config (key TEXT PRIMARY KEY, val TEXT);")


def load_overrides(db_path: str | None = None) -> dict[str, Any]:
    path = get_config_db_path(db_path)
    init_config_table(path)
    with _lock, sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT key, val FROM runtime_config").fetchall()
    return {k: json.loads(v) for k, v in rows}


def set_override(key: str, value: Any, db_path: str | None = None) -> None:
    path = get_config_db_path(db_path)
    init_config_table(path)
    with _lock, sqlite3.connect(path) as conn:
        conn.execute("INSERT OR REPLACE INTO runtime_config (key, val) VALUES (?, ?)", (key, json.dumps(value)))


def remove_override(key: str, db_path: str | None = None) -> None:
    path = get_config_db_path(db_path)
    init_config_table(path)
    with _lock, sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM runtime_config WHERE key = ?", (key,))
