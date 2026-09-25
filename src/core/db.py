"""
db.py — SQLite Local Durable Store for Weighment Outbox Spool
=============================================================
Thread-safe, write-ahead logged SQLite persistence layer ensuring zero data loss
and duplicate-free cloud transmission across offline events, reboots, and network drops.
"""

from __future__ import annotations

import logging
import os
import random
import sqlite3
import threading
import time
from typing import Any

from src.config import config
from src.config.constants import (
    DEFAULT_DB_PATH,
    SPOOL_BASE_RETRY_DELAY,
    SPOOL_LEASE_DURATION_S,
    SPOOL_MAX_RETRY_DELAY,
)

logger = logging.getLogger(__name__)

_db_lock = threading.RLock()
_db_path: str | None = None


def get_default_db_path() -> str:
    """Computes the absolute path to the default SQLite database."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, DEFAULT_DB_PATH)


def init_db(db_path: str | None = None) -> None:
    """Initializes SQLite database with WAL mode and schema."""
    global _db_path
    with _db_lock:
        if db_path is None:
            _db_path = get_default_db_path()
        else:
            _db_path = db_path

        dir_name = os.path.dirname(_db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        with sqlite3.connect(_db_path) as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("PRAGMA foreign_keys = ON;")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS weighment_spool (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    created_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    weight REAL NOT NULL,
                    anpr_plate TEXT NOT NULL,
                    detected_vehicle_number TEXT NOT NULL,
                    center_id INTEGER NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    lease_until REAL NOT NULL DEFAULT 0.0,
                    next_retry_at REAL NOT NULL DEFAULT 0.0,
                    last_error TEXT,
                    last_attempt_at REAL,
                    cloud_entry_id TEXT,
                    acknowledged_at REAL
                );
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS spool_images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    camera_name TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    image_data BLOB NOT NULL,
                    content_type TEXT NOT NULL DEFAULT 'image/jpeg',
                    FOREIGN KEY (session_id) REFERENCES weighment_spool(session_id) ON DELETE CASCADE
                );
                """
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_spool_status ON weighment_spool(status, next_retry_at, lease_until);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_spool_session ON weighment_spool(session_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_images_session ON spool_images(session_id);"
            )
            conn.commit()

        logger.info(f"[Spool DB] Initialized SQLite outbox spool database at: {_db_path}")


def _get_connection() -> sqlite3.Connection:
    if _db_path is None:
        init_db()
    assert _db_path is not None
    conn = sqlite3.connect(_db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def spool_weighment(session_package: dict[str, Any]) -> str:
    """
    Atomically writes weighment record and camera images to SQLite with status PENDING.
    Guarantees persistence before any cloud upload attempt.
    """
    from src.integrations.gluvok import sanitize_vehicle_number

    session_id = str(session_package.get("session_id", f"SESS_{int(time.time())}"))
    weight = float(session_package.get("weight", 0.0))
    raw_plate = str(session_package.get("anpr_plate", "NO_PLATE_DETECTED"))
    detected_plate, _ = sanitize_vehicle_number(raw_plate)
    center_id = int(config.center_id)
    now = time.time()

    with _db_lock, _get_connection() as conn:
        # Idempotent insert: if session_id already exists, ignore duplicate insert
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO weighment_spool (
                session_id, created_at, status, weight, anpr_plate,
                detected_vehicle_number, center_id, next_retry_at
            ) VALUES (?, ?, 'PENDING', ?, ?, ?, ?, ?);
            """,
            (session_id, now, round(weight, 3), raw_plate, detected_plate, center_id, now),
        )

        if cursor.rowcount > 0:
            # Store primary Camera 1 snapshot
            cam1_bytes = session_package.get("cam1_final_image")
            if cam1_bytes and isinstance(cam1_bytes, bytes):
                conn.execute(
                    """
                    INSERT INTO spool_images (
                        session_id, camera_name, filename, image_data, content_type
                    ) VALUES (?, 'cam1', ?, ?, 'image/jpeg');
                    """,
                    (session_id, f"{session_id}_cam1.jpg", cam1_bytes),
                )

            # Store any auxiliary camera snapshots
            aux_dict = session_package.get("auxiliary_images", {})
            if isinstance(aux_dict, dict):
                for cam_idx in sorted(aux_dict.keys(), key=lambda k: str(k)):
                    img_bytes = aux_dict[cam_idx]
                    if img_bytes and isinstance(img_bytes, bytes):
                        str_idx = str(cam_idx)
                        cam_name = str_idx if str_idx.startswith(("anpr_", "aux_")) else f"aux_{str_idx}"
                        conn.execute(
                            """
                            INSERT INTO spool_images (
                                session_id, camera_name, filename, image_data, content_type
                            ) VALUES (?, ?, ?, ?, 'image/jpeg');
                            """,
                            (session_id, cam_name, f"{session_id}_{cam_name}.jpg", img_bytes),
                        )
            conn.commit()
            logger.info(
                f"[Spool DB] Spooled session {session_id} ({detected_plate}, {weight:.3f} kg) to SQLite."
            )
        else:
            logger.warning(
                f"[Spool DB] Session {session_id} already exists in spool DB. Duplicate insertion avoided."
            )

    return session_id


def acquire_next_spool_task(lease_seconds: float = SPOOL_LEASE_DURATION_S) -> dict[str, Any] | None:
    """
    Atomically acquires and leases the next eligible record for upload (FIFO).
    Prevents race conditions between worker ticks and concurrent callers.
    """
    now = time.time()
    lease_deadline = now + lease_seconds

    with _db_lock, _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, session_id, weight, detected_vehicle_number, center_id, retry_count
            FROM weighment_spool
            WHERE status IN ('PENDING', 'RETRY')
              AND next_retry_at <= ?
              AND lease_until < ?
            ORDER BY created_at ASC
            LIMIT 1;
            """,
            (now, now),
        )
        row = cursor.fetchone()
        if not row:
            return None

        record_id = row["id"]
        cursor.execute(
            """
            UPDATE weighment_spool
            SET status = 'UPLOADING',
                lease_until = ?,
                last_attempt_at = ?
            WHERE id = ?;
            """,
            (lease_deadline, now, record_id),
        )
        conn.commit()
        return dict(row)


def get_spool_images(session_id: str) -> list[tuple[str, str, bytes]]:
    """Returns list of (camera_name, filename, image_bytes) for a session."""
    with _db_lock, _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT camera_name, filename, image_data
            FROM spool_images
            WHERE session_id = ?
            ORDER BY id ASC;
            """,
            (session_id,),
        )
        return [(r["camera_name"], r["filename"], r["image_data"]) for r in cursor.fetchall()]


def mark_spool_acknowledged(session_id: str, cloud_entry_id: str | None = None) -> None:
    """Marks record as successfully ACKNOWLEDGED with cloud confirmation."""
    now = time.time()
    with _db_lock, _get_connection() as conn:
        conn.execute(
            """
            UPDATE weighment_spool
            SET status = 'ACKNOWLEDGED',
                lease_until = 0.0,
                cloud_entry_id = ?,
                acknowledged_at = ?
            WHERE session_id = ?;
            """,
            (str(cloud_entry_id or ""), now, session_id),
        )
        conn.commit()
        logger.info(f"[Spool DB] Session {session_id} acknowledged by cloud (Entry ID: {cloud_entry_id}).")


def mark_spool_retry(
    session_id: str,
    error_msg: str,
    is_terminal: bool = False,
) -> None:
    """
    Marks record for retry with exponential backoff and jitter, releasing lease lock.
    If is_terminal is True, flags as FAILED_TERMINAL.
    """
    now = time.time()
    with _db_lock, _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT retry_count FROM weighment_spool WHERE session_id = ?;",
            (session_id,),
        )
        row = cursor.fetchone()
        current_retries = row["retry_count"] if row else 0

        if is_terminal:
            cursor.execute(
                """
                UPDATE weighment_spool
                SET status = 'FAILED_TERMINAL',
                    lease_until = 0.0,
                    last_error = ?
                WHERE session_id = ?;
                """,
                (error_msg, session_id),
            )
        else:
            new_retries = current_retries + 1
            base_delay = min(SPOOL_MAX_RETRY_DELAY, SPOOL_BASE_RETRY_DELAY * (2 ** min(new_retries, 6)))
            jitter = random.uniform(0.5, 2.5)
            next_retry = now + base_delay + jitter

            cursor.execute(
                """
                UPDATE weighment_spool
                SET status = 'RETRY',
                    retry_count = ?,
                    next_retry_at = ?,
                    lease_until = 0.0,
                    last_error = ?
                WHERE session_id = ?;
                """,
                (new_retries, next_retry, error_msg, session_id),
            )
        conn.commit()


def recover_stranded_leases(force: bool = False) -> int:
    """
    Recovers any tasks stranded in UPLOADING due to unexpected power outage or crash.
    Safely resets them to PENDING so they can be dispatched.
    If force is True, resets all UPLOADING tasks regardless of lease_until (used on daemon boot).
    """
    now = time.time()
    with _db_lock, _get_connection() as conn:
        cursor = conn.cursor()
        if force:
            cursor.execute(
                """
                UPDATE weighment_spool
                SET status = 'PENDING',
                    lease_until = 0.0
                WHERE status = 'UPLOADING';
                """
            )
        else:
            cursor.execute(
                """
                UPDATE weighment_spool
                SET status = 'PENDING',
                    lease_until = 0.0
                WHERE status = 'UPLOADING'
                  AND lease_until < ?;
                """,
                (now,),
            )
        count = cursor.rowcount
        conn.commit()
        if count > 0:
            logger.info(f"[Spool DB] Recovered {count} stranded upload tasks back to PENDING.")
        return count


def get_spool_stats() -> dict[str, int]:
    """Returns queue status counts for telemetry and web dashboard."""
    with _db_lock, _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT status, COUNT(*) as cnt
            FROM weighment_spool
            GROUP BY status;
            """
        )
        counts: dict[str, int] = {
            "pending": 0,
            "uploading": 0,
            "acknowledged": 0,
            "retry": 0,
            "failed_terminal": 0,
        }
        for row in cursor.fetchall():
            st = str(row["status"]).lower()
            counts[st] = int(row["cnt"])

        counts["total"] = sum(counts.values())
        return counts


def reset_db() -> None:
    """Clears all spool tables. Used exclusively for testing fixtures."""
    with _db_lock, _get_connection() as conn:
        conn.execute("DELETE FROM spool_images;")
        conn.execute("DELETE FROM weighment_spool;")
        conn.commit()


__all__ = [
    "acquire_next_spool_task",
    "get_default_db_path",
    "get_spool_images",
    "get_spool_stats",
    "init_db",
    "mark_spool_acknowledged",
    "mark_spool_retry",
    "recover_stranded_leases",
    "reset_db",
    "spool_weighment",
]
