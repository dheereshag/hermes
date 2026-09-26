"""
session.py — Weighbridge Session Lifecycle Orchestrator
======================================================
Manages weighbridge session lifecycle, Camera 1 ANPR capture loop thread,
auxiliary camera snapshots, 10-second post-stabilization timing, and data packaging.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from enum import Enum
from typing import Any

import requests

from src.config.constants import (
    ANPR_CAPTURE_INTERVAL,
    POST_STABILITY_DURATION,
)
from src.core.telemetry import record_system_event, record_weighment_result
from src.devices.camera import (
    capture_all_camera_snapshots,
    capture_anpr_snapshots,
    fetch_image_bytes,
)
from src.integrations.anpr import (
    get_highest_frequency_plate,
    send_frame_to_anpr_server,
)
from src.services.image_compressor import compress_image_bytes

logger = logging.getLogger(__name__)

__all__ = [
    "SessionPhase",
    "WeighbridgeSessionManager",
    "fetch_image_bytes",
]



class SessionPhase(Enum):
    PHASE_IDLE = 0
    PHASE_STABILIZING = 1          # Weight active, 2s Multi-ANPR OCR running
    PHASE_POST_STABILITY = 2       # Weight stable, Full fleet cameras captured, +10s timer running
    PHASE_COMPLETED = 3            # Session finished & transmitted, awaiting weight return to 0


class WeighbridgeSessionManager:
    def __init__(self):
        self.phase = SessionPhase.PHASE_IDLE
        self.session_id: str | None = None
        self.stable_weight: float = 0.0

        self._anpr_plates: list[str] = []
        self._anpr_statuses: list[str] = []
        self._anpr_frame_buffers: dict[int, list[bytes]] = {}
        self._fleet_snapshots: dict[str, bytes | None] = {}

        self._anpr_thread: threading.Thread | None = None
        self._fleet_snapshot_thread: threading.Thread | None = None
        self._stop_anpr_event = threading.Event()

        self._post_stability_start_time: float = 0.0
        self._lock = threading.Lock()

    def start_session(self):
        """Called when scale weight exceeds threshold (start of weighment session)."""
        with self._lock:
            if self.phase != SessionPhase.PHASE_IDLE:
                return

            if self._anpr_thread and self._anpr_thread.is_alive():
                self._stop_anpr_event.set()
                old_thread = self._anpr_thread
                self._anpr_thread = None
            else:
                old_thread = None

            self.session_id = f"SESS_{int(time.time())}_{uuid.uuid4().hex[:6]}"
            self.phase = SessionPhase.PHASE_STABILIZING
            self.stable_weight = 0.0
            self._anpr_plates.clear()
            self._anpr_statuses.clear()
            self._anpr_frame_buffers.clear()
            self._fleet_snapshots.clear()
            self._stop_anpr_event = threading.Event()

            logger.info(f"[Session] Started new weighbridge session: {self.session_id}")

            current_session_id = self.session_id
            current_stop_event = self._stop_anpr_event

            self._anpr_thread = threading.Thread(
                target=self._anpr_loop,
                args=(current_session_id, current_stop_event),
                name=f"ANPRLoop_{self.session_id}",
                daemon=True,
            )
            self._anpr_thread.start()

        if old_thread and old_thread.is_alive():
            old_thread.join(timeout=0.3)

    def _capture_and_record_anpr_sample(self) -> None:
        """Fetch frames from all configured ANPR cameras in parallel, buffer them, and query Argus."""
        snapshots = capture_anpr_snapshots()
        if not snapshots:
            logger.warning("[ANPR] No ANPR cameras available or configured.")
            return

        for cam_idx, _cam_url, img_bytes in snapshots:
            if not img_bytes:
                logger.warning(f"[ANPR] Camera {cam_idx} frame capture failed from {_cam_url}")
                continue

            with self._lock:
                buf = self._anpr_frame_buffers.setdefault(cam_idx, [])
                if len(buf) >= 5:
                    buf.pop(0)
                buf.append(img_bytes)

            logger.info(f"[ANPR] Camera {cam_idx} snapshot captured ({len(img_bytes)} bytes). Sending to Argus...")
            plate, status_code = send_frame_to_anpr_server(img_bytes)
            with self._lock:
                if plate:
                    self._anpr_plates.append(plate)
                self._anpr_statuses.append(status_code)
                sample_count = len(self._anpr_plates)

            if plate:
                logger.info(
                    f"[ANPR] Camera {cam_idx} -> Argus response: Plate='{plate}' "
                    f"(Status={status_code}, Valid plates collected: {sample_count})"
                )
            else:
                logger.info(
                    f"[ANPR] Camera {cam_idx} -> Argus response: No plate detected (Status={status_code})"
                )

    def _anpr_loop(self, session_id: str, stop_event: threading.Event):
        """Background thread executing 2-second multi-camera capture & ANPR requests."""
        logger.info(f"[Session {session_id}] Multi-camera ANPR capture loop started.")
        while not stop_event.is_set():
            with self._lock:
                if self.session_id != session_id or self.phase == SessionPhase.PHASE_IDLE:
                    break

            loop_start = time.time()
            try:
                self._capture_and_record_anpr_sample()
            except (requests.RequestException, OSError, ValueError, RuntimeError) as e:
                logger.error(f"[Session {session_id}] Exception in ANPR loop iteration: {e}")

            if stop_event.is_set():
                break
            with self._lock:
                if self.session_id != session_id or self.phase == SessionPhase.PHASE_IDLE:
                    break

            elapsed = time.time() - loop_start
            sleep_time = max(0.1, ANPR_CAPTURE_INTERVAL - elapsed)
            if stop_event.wait(timeout=sleep_time):
                break

        logger.info(f"[Session {session_id}] Multi-camera ANPR capture loop stopped.")

    def trigger_mid_stability_fleet_capture(self) -> None:
        """Trigger parallel fleet capture and background pre-compression halfway through stability."""
        with self._lock:
            if self.phase != SessionPhase.PHASE_STABILIZING:
                return
            if self._fleet_snapshot_thread and self._fleet_snapshot_thread.is_alive():
                return
            logger.info(
                f"[Session {self.session_id}] Mid-stability mark reached. "
                "Triggering all-camera snapshots and pre-compressing in background..."
            )
            self._fleet_snapshot_thread = threading.Thread(
                target=self._capture_all_cameras_in_background,
                name=f"FleetCapture_{self.session_id}",
                daemon=True,
            )
            self._fleet_snapshot_thread.start()

    def on_weight_stabilized(self, weight: float):
        """Called when scale stability machine confirms 10s weight stability."""
        with self._lock:
            if self.phase != SessionPhase.PHASE_STABILIZING:
                return

            self.phase = SessionPhase.PHASE_POST_STABILITY
            self.stable_weight = weight
            self._post_stability_start_time = time.time()
            logger.info(
                f"[Session {self.session_id}] Weight stabilized at {weight:.3f} kg. "
                f"Starting {POST_STABILITY_DURATION:.1f}s post-stabilization countdown..."
            )

        need_fleet_thread = False
        with self._lock:
            if not self._fleet_snapshots and (
                not self._fleet_snapshot_thread or not self._fleet_snapshot_thread.is_alive()
            ):
                need_fleet_thread = True
        if need_fleet_thread:
            self._fleet_snapshot_thread = threading.Thread(
                target=self._capture_all_cameras_in_background,
                name=f"FleetCapture_{self.session_id}",
                daemon=True,
            )
            self._fleet_snapshot_thread.start()

    def _capture_all_cameras_in_background(self) -> None:
        """Background worker to fetch full-fleet snapshots and pre-compress them in RAM."""
        try:
            snapshots = capture_all_camera_snapshots()
            compressed: dict[str, bytes | None] = {}
            for label, img_bytes in snapshots.items():
                compressed[label] = compress_image_bytes(img_bytes) if img_bytes else None
            with self._lock:
                if self.phase in (
                    SessionPhase.PHASE_STABILIZING,
                    SessionPhase.PHASE_POST_STABILITY,
                    SessionPhase.PHASE_COMPLETED,
                ):
                    self._fleet_snapshots = compressed
                    logger.info(
                        f"[Session {self.session_id}] {len(compressed)} fleet snapshots "
                        "captured and compressed in RAM."
                    )
        except (requests.RequestException, OSError, ValueError, RuntimeError) as e:
            logger.error(f"[Session {self.session_id}] Error capturing full-fleet cameras: {e}")

    def check_session_progress(self) -> dict[str, Any] | None:
        """Checks if post-stabilization timer expired. Finalizes session immediately without blocking."""
        with self._lock:
            if self.phase != SessionPhase.PHASE_POST_STABILITY:
                return None

            elapsed = time.time() - self._post_stability_start_time
            if elapsed < POST_STABILITY_DURATION:
                return None

            logger.info(
                f"[Session {self.session_id}] Post-stabilization {POST_STABILITY_DURATION:.1f}s completed. "
                "Finalizing session package immediately (stopping ANPR without blocking)..."
            )
            self.phase = SessionPhase.PHASE_COMPLETED
            self._stop_anpr_event.set()

        return self._finalize_session_package()

    def _finalize_session_package(self) -> dict[str, Any]:
        """Assembles final session dictionary data."""
        if self._fleet_snapshot_thread and self._fleet_snapshot_thread.is_alive():
            self._fleet_snapshot_thread.join(timeout=0.3)

        with self._lock:
            if self._anpr_plates:
                final_anpr_plate = get_highest_frequency_plate(self._anpr_plates)
            else:
                final_anpr_plate = "NO_PLATE_DETECTED"

            fleet_copy: dict[str, bytes | None] = dict(self._fleet_snapshots)
            for cam_idx, frames in self._anpr_frame_buffers.items():
                label = f"anpr_{cam_idx}"
                if not fleet_copy.get(label) and frames:
                    fleet_copy[label] = compress_image_bytes(frames[-1])

            total_samples = len(self._anpr_plates)
            total_frames = sum(len(f) for f in self._anpr_frame_buffers.values())

            package = {
                "session_id": self.session_id,
                "weight": round(self.stable_weight, 3),
                "anpr_plate": final_anpr_plate,
                "camera_snapshots": fleet_copy,
                "total_anpr_samples": total_samples,
                "total_anpr_frames": total_frames,
                "timestamp": time.time(),
            }

            self._anpr_frame_buffers.clear()
            self._fleet_snapshots.clear()

            logger.info(
                f"[Session {self.session_id}] Package finalized: "
                f"Plate='{final_anpr_plate}', Weight={self.stable_weight:.3f} kg, "
                f"Total Snapshots={len(fleet_copy)}"
            )
            is_err = bool(not self._anpr_plates)
            _record_session_telemetry(self.session_id, final_anpr_plate, self.stable_weight, is_err)
            return package

    def reset_session(self):
        """Resets session manager state when weight returns to zero (scale idle)."""
        with self._lock:
            if self.phase == SessionPhase.PHASE_IDLE:
                return

            logger.info(f"[Session {self.session_id}] Weight zeroed. Resetting session manager.")
            self._stop_anpr_event.set()
            old_anpr_thread = self._anpr_thread
            self._anpr_thread = None
            self._stop_anpr_event = threading.Event()
            self._fleet_snapshot_thread = None
            self.phase = SessionPhase.PHASE_IDLE
            self.session_id = None
            self.stable_weight = 0.0
            self._anpr_frame_buffers.clear()
            self._anpr_plates.clear()
            self._anpr_statuses.clear()
            self._fleet_snapshots.clear()

        if old_anpr_thread and old_anpr_thread.is_alive():
            old_anpr_thread.join(timeout=0.3)


def _record_session_telemetry(
    session_id: str | None,
    plate: str,
    weight: float,
    is_error: bool,
) -> None:
    """Bridge completed session outcome to core telemetry store."""
    try:
        record_weighment_result(
            session_id=str(session_id),
            plate=plate,
            weight=weight,
            is_error=is_error,
            status_code=plate if is_error else "SUCCESS",
        )
        record_system_event(
            "WEIGHMENT",
            f"Session {session_id}: {weight:.3f} kg -> Plate: '{plate}'",
        )
    except (ImportError, AttributeError, ValueError) as e:
        logger.debug(f"[Session] Error recording live telemetry: {e}")


# Module-level singleton
session_manager = WeighbridgeSessionManager()

__all__ = [
    "SessionPhase",
    "WeighbridgeSessionManager",
    "session_manager",
]
