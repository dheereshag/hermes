"""
spool.py — Background Outbox Spool Dispatcher & Retry Worker
=============================================================
Runs sequential, single-flight FIFO dispatching of weighment records from SQLite
to Gluvok Cloud API with anti-duplication verification, exponential backoff, and crash recovery.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from src.config.constants import (
    SPOOL_LEASE_DURATION_S,
    SPOOL_WORKER_POLL_INTERVAL,
)
from src.core.db import (
    acquire_next_spool_task,
    get_spool_images,
    mark_spool_acknowledged,
    mark_spool_retry,
    recover_stranded_leases,
)
from src.core.telemetry import record_system_event

logger = logging.getLogger(__name__)


class SpoolWorker:
    """
    Background worker that manages the durable SQLite outbox queue.
    Guarantees strictly sequential, single-flight uploads to prevent duplicate submissions.
    """

    def __init__(self, poll_interval: float = SPOOL_WORKER_POLL_INTERVAL):
        self.poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._is_running = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Starts the spool worker in a background daemon thread."""
        with self._lock:
            if self._is_running:
                return

            self._is_running = True
            self._stop_event.clear()
            self._wake_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="SpoolWorker",
                daemon=True,
            )
            self._thread.start()
            logger.info("[SpoolWorker] Background outbox spool dispatcher started.")

    def stop(self) -> None:
        """Stops the spool worker thread gracefully."""
        with self._lock:
            if not self._is_running:
                return

            self._is_running = False
            self._stop_event.set()
            self._wake_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("[SpoolWorker] Background outbox spool dispatcher stopped.")

    def notify_new_record(self) -> None:
        """Wakes up worker immediately when a new weighment is spooled."""
        self._wake_event.set()

    def _process_single_task(self, task: dict[str, Any]) -> bool:
        """
        Executes transmission of a leased weighment task.
        Returns True if a task was processed.
        """
        from src.integrations.gluvok import (
            transmit_entry_multipart,
            verify_entry_in_cloud,
        )

        session_id = str(task["session_id"])
        center_id = int(task["center_id"])
        vehicle_num = str(task["detected_vehicle_number"])
        weight = float(task["weight"])


        # Fetch all camera images for this session from DB
        images = get_spool_images(session_id)
        image_attachments = [
            (filename, data)
            for _, filename, data in images
            if data and isinstance(data, bytes) and len(data) > 0
        ]

        logger.info(
            f"[SpoolWorker] Dispatching leased session {session_id} to cloud with "
            f"{len(image_attachments)} camera image(s)..."
        )

        success, entry_id, error_msg, is_read_timeout = transmit_entry_multipart(
            center_id=center_id,
            detected_vehicle_number=vehicle_num,
            weight=weight,
            images=image_attachments,
        )

        if success:
            mark_spool_acknowledged(session_id, entry_id)
            record_system_event(
                "SPOOL",
                f"Session {session_id} uploaded to cloud -> Entry #{entry_id}",
            )
            return True

        # Handle ambiguous ReadTimeout: Did cloud receive and commit before the connection dropped?
        if is_read_timeout:
            logger.info(
                f"[SpoolWorker] Ambiguous read timeout for {session_id}. "
                f"Executing pre-retry verification query..."
            )
            verified_entry_id = verify_entry_in_cloud(center_id, vehicle_num, weight)
            if verified_entry_id:
                mark_spool_acknowledged(session_id, verified_entry_id)
                record_system_event(
                    "SPOOL",
                    f"Session {session_id} verified in cloud as #{verified_entry_id}. Duplicate avoided.",
                )
                return True

        # Determine if terminal failure (e.g. 400 Bad Request)
        is_terminal = bool(error_msg and "HTTP 400" in error_msg)
        mark_spool_retry(session_id, error_msg or "Unknown transmission error", is_terminal=is_terminal)
        record_system_event(
            "SPOOL",
            f"Session {session_id} delivery failed: {error_msg}. Queued for retry.",
        )
        return True

    def _run_loop(self) -> None:
        """Main dispatcher loop running until stopped."""
        # Initial recovery of any stranded tasks
        import sqlite3

        try:
            recover_stranded_leases()
        except (sqlite3.Error, OSError) as e:
            logger.error(f"[SpoolWorker] Error during initial lease recovery: {e}")

        while not self._stop_event.is_set():
            try:
                # Keep processing eligible records in FIFO order
                task_processed = False
                while not self._stop_event.is_set():
                    task = acquire_next_spool_task(lease_seconds=SPOOL_LEASE_DURATION_S)
                    if not task:
                        break
                    self._process_single_task(task)
                    task_processed = True

                # If we processed tasks, reset wake event and take a short pause
                if task_processed:
                    self._wake_event.clear()

            except (sqlite3.Error, OSError, ValueError, RuntimeError):
                logger.exception("[SpoolWorker] Unexpected error in worker loop")


            # Sleep until timeout or wake event
            self._wake_event.wait(timeout=self.poll_interval)
            self._wake_event.clear()


# Module-level singleton
spool_worker = SpoolWorker()

__all__ = [
    "SpoolWorker",
    "spool_worker",
]
