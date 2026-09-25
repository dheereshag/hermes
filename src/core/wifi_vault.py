"""wifi_vault.py — Persistent Wi-Fi Network Vault."""
from __future__ import annotations

import sqlite3
import threading
from typing import Any

from src.core.db import get_default_db_path

_vault_lock = threading.RLock()
_TABLE_SQL = "CREATE TABLE IF NOT EXISTS wifi_networks (ssid TEXT PRIMARY KEY, password TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"


def _get_conn(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or get_default_db_path(), timeout=5.0)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute(_TABLE_SQL)
    return conn


def save_wifi_network(ssid: str, password: str, db_path: str | None = None) -> None:
    """Upserts Wi-Fi credentials and updates last_connected_at."""
    sql = "INSERT INTO wifi_networks (ssid, password, last_connected_at) VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(ssid) DO UPDATE SET password = excluded.password, last_connected_at = CURRENT_TIMESTAMP;"
    with _vault_lock, _get_conn(db_path) as conn:
        conn.execute(sql, (ssid, password))


def get_saved_wifi_networks(db_path: str | None = None) -> list[dict[str, Any]]:
    """Returns saved networks without exposing passwords."""
    sql = "SELECT ssid, created_at, last_connected_at FROM wifi_networks ORDER BY last_connected_at DESC"
    with _vault_lock, _get_conn(db_path) as conn:
        rows = conn.execute(sql).fetchall()
        return [{"ssid": r["ssid"], "created_at": r["created_at"], "last_connected_at": r["last_connected_at"]} for r in rows]


def get_wifi_password(ssid: str, db_path: str | None = None) -> str | None:
    """Retrieves stored password for given SSID."""
    with _vault_lock, _get_conn(db_path) as conn:
        row = conn.execute("SELECT password FROM wifi_networks WHERE ssid = ?", (ssid,)).fetchone()
        return str(row["password"]) if row else None


def delete_saved_wifi_network(ssid: str, db_path: str | None = None) -> bool:
    """Deletes network from vault."""
    with _vault_lock, _get_conn(db_path) as conn:
        return conn.execute("DELETE FROM wifi_networks WHERE ssid = ?", (ssid,)).rowcount > 0


def clear_saved_wifi_networks(db_path: str | None = None) -> None:
    """Removes all saved networks from vault."""
    with _vault_lock, _get_conn(db_path) as conn:
        conn.execute("DELETE FROM wifi_networks;")
