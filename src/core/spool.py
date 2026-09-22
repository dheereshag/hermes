"""
spool.py — Background Outbox Spool Dispatcher & Retry Worker
=============================================================
Runs sequential, single-flight FIFO dispatching of weighment records from SQLite
to Gluvok Cloud API with anti-duplication verification, exponential backoff, and crash recovery.
"""

from __future__ import annotations

import logging
import sqlite3
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

    def _extract_task_images(self, session_id: str) -> list[tuple[str, bytes]]:
        """Retrieves and validates all stored camera image blobs for this session."""
        images = get_spool_images(session_id)
        return [
            (filename, data)
            for _, filename, data in images
            if data and isinstance(data, bytes) and len(data) > 0
        ]

    def _handle_transmission_outcome(
        self,
        session_id: str,
        center_id: int,
        vehicle_num: str,
        weight: float,
        success: bool,
        entry_id: str | None,
        error_msg: str | None,
        is_read_timeout: bool,
    ) -> None:
        """Processes upload response, anti-duplication pre-retry check, and backoff queueing."""
        if success:
            mark_spool_acknowledged(session_id, entry_id)
            record_system_event("SPOOL", f"Session {session_id} uploaded to cloud -> Entry #{entry_id}")
            return

        # Handle ambiguous ReadTimeout: Did cloud receive and commit before the connection dropped?
        if is_read_timeout:
            from src.integrations.gluvok import verify_entry_in_cloud

            logger.info(
                f"[SpoolWorker] Ambiguous read timeout for {session_id}. Executing pre-retry verification query..."
            )
            verified_entry_id = verify_entry_in_cloud(center_id, vehicle_num, weight)
            if verified_entry_id:
                mark_spool_acknowledged(session_id, verified_entry_id)
                record_system_event(
                    "SPOOL",
                    f"Session {session_id} verified in cloud as #{verified_entry_id}. Duplicate avoided.",
                )
                return

        # Terminal client errors (400 Bad Request, 422 Unprocessable Entity)
        is_terminal = bool(error_msg and ("HTTP 400" in error_msg or "HTTP 422" in error_msg))
        mark_spool_retry(session_id, error_msg or "Unknown transmission error", is_terminal=is_terminal)
        record_system_event("SPOOL", f"Session {session_id} delivery failed: {error_msg}. Queued for retry.")

    def _process_single_task(self, task: dict[str, Any]) -> bool:
        """Executes transmission of a leased weighment task."""
        from src.integrations.gluvok import transmit_entry_multipart

        session_id = str(task["session_id"])
        center_id = int(task["center_id"])
        vehicle_num = str(task["detected_vehicle_number"])
        weight = float(task["weight"])

        image_attachments = self._extract_task_images(session_id)
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

        self._handle_transmission_outcome(
            session_id=session_id,
            center_id=center_id,
            vehicle_num=vehicle_num,
            weight=weight,
            success=success,
            entry_id=entry_id,
            error_msg=error_msg,
            is_read_timeout=is_read_timeout,
        )
        return True

    def _run_loop(self) -> None:
        """Main dispatcher loop running until stopped."""
        try:
            recover_stranded_leases(force=True)
        except (sqlite3.Error, OSError) as e:
            logger.error(f"[SpoolWorker] Error during initial lease recovery: {e}")

        while not self._stop_event.is_set():
            try:
                # Reclaim any expired leases periodically
                recover_stranded_leases(force=False)

                # Process all available tasks in FIFO order
                while not self._stop_event.is_set():
                    task = acquire_next_spool_task(lease_seconds=SPOOL_LEASE_DURATION_S)
                    if not task:
                        break
                    self._process_single_task(task)

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
