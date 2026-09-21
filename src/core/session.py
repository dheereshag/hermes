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
    capture_anpr_snapshots,
    capture_auxiliary_snapshots,
    fetch_image_bytes,
)
from src.integrations.anpr import (
    get_highest_frequency_plate,
    send_frame_to_anpr_server,
)

logger = logging.getLogger(__name__)

__all__ = [
    "SessionPhase",
    "WeighbridgeSessionManager",
    "fetch_image_bytes",
]



class SessionPhase(Enum):
    PHASE_IDLE = 0
    PHASE_STABILIZING = 1          # Weight active, 2s Cam 1 ANPR running
    PHASE_POST_STABILITY = 2       # Weight stable, Aux cams captured, +10s timer running
    PHASE_COMPLETED = 3            # Session finished & transmitted, awaiting weight return to 0


class WeighbridgeSessionManager:
    def __init__(self):
        self.phase = SessionPhase.PHASE_IDLE
        self.session_id: str | None = None
        self.stable_weight: float = 0.0

        self._cam1_frames: list[bytes] = []
        self._cam1_plates: list[str] = []
        self._cam1_statuses: list[str] = []
        self._auxiliary_images: dict[int, bytes | None] = {}
        self._secondary_anpr_images: dict[int, bytes | None] = {}

        self._anpr_thread: threading.Thread | None = None
        self._aux_thread: threading.Thread | None = None
        self._stop_anpr_event = threading.Event()

        self._post_stability_start_time: float = 0.0
        self._lock = threading.Lock()

    def start_session(self):
        """Called when scale weight exceeds threshold (start of weighment session)."""
        with self._lock:
            if self.phase != SessionPhase.PHASE_IDLE:
                return

            # Ensure any lingering thread from previous session is stopped
            if self._anpr_thread and self._anpr_thread.is_alive():
                self._stop_anpr_event.set()
                old_thread = self._anpr_thread
                self._anpr_thread = None
            else:
                old_thread = None

            self.session_id = f"SESS_{int(time.time())}_{uuid.uuid4().hex[:6]}"
            self.phase = SessionPhase.PHASE_STABILIZING
            self.stable_weight = 0.0
            self._cam1_frames.clear()
            self._cam1_plates.clear()
            self._cam1_statuses.clear()
            self._auxiliary_images.clear()
            self._secondary_anpr_images.clear()
            self._stop_anpr_event = threading.Event()

            logger.info(f"[Session] Started new weighbridge session: {self.session_id}")

            current_session_id = self.session_id
            current_stop_event = self._stop_anpr_event

            # Launch Camera ANPR capture loop thread bound to this session
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
            return

        for cam_idx, _cam_url, img_bytes in snapshots:
            if not img_bytes:
                continue

            with self._lock:
                if cam_idx == 1:
                    if len(self._cam1_frames) >= 5:
                        self._cam1_frames.pop(0)
                    self._cam1_frames.append(img_bytes)
                else:
                    self._secondary_anpr_images[cam_idx] = img_bytes

            plate, status_code = send_frame_to_anpr_server(img_bytes)
            with self._lock:
                if plate:
                    self._cam1_plates.append(plate)
                self._cam1_statuses.append(status_code)

    def _anpr_loop(self, session_id: str, stop_event: threading.Event):
        """Background thread executing 2-second Camera 1 capture & ANPR requests."""
        logger.info(f"[Session {session_id}] Camera 1 ANPR capture loop started.")
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

        logger.info(f"[Session {session_id}] Camera 1 ANPR capture loop stopped.")

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
                f"Triggering auxiliary camera snapshots and starting +10s countdown..."
            )

        # Concurrently capture auxiliary overview cameras (2 ... N) in background thread
        self._aux_thread = threading.Thread(
            target=self._capture_auxiliary_in_background,
            name=f"AuxCapture_{self.session_id}",
            daemon=True,
        )
        self._aux_thread.start()

    def _capture_auxiliary_in_background(self) -> None:
        """Background worker to fetch auxiliary snapshots without stalling real-time scale reads."""
        try:
            aux_images = capture_auxiliary_snapshots()
            with self._lock:
                if self.phase in (SessionPhase.PHASE_POST_STABILITY, SessionPhase.PHASE_COMPLETED):
                    self._auxiliary_images = aux_images
        except (requests.RequestException, OSError, ValueError, RuntimeError) as e:
            logger.error(f"[Session {self.session_id}] Error capturing auxiliary cameras: {e}")

    def check_session_progress(self) -> dict[str, Any] | None:
        """
        Periodically called in loop. Checks if 10-second post-stabilization timer expired.
        If expired, finalizes session, stops ANPR loop, and returns full session package.
        """
        with self._lock:
            if self.phase != SessionPhase.PHASE_POST_STABILITY:
                return None

            elapsed = time.time() - self._post_stability_start_time
            if elapsed < POST_STABILITY_DURATION:
                return None  # Still waiting out the 10-second post-stabilization period

            logger.info(
                f"[Session {self.session_id}] Post-stabilization 10s completed. "
                f"Finalizing session package..."
            )
            self.phase = SessionPhase.PHASE_COMPLETED
            self._stop_anpr_event.set()

        # Build final session package
        final_package = self._finalize_session_package()
        return final_package

    def _finalize_session_package(self) -> dict[str, Any]:
        """Assembles final session dictionary data."""
        if self._aux_thread and self._aux_thread.is_alive():
            self._aux_thread.join(timeout=1.0)

        with self._lock:
            if self._cam1_plates:
                final_anpr_plate = get_highest_frequency_plate(self._cam1_plates)
            elif self._cam1_statuses:
                # Forward the exact Argus error/status code as the plate value to Gluvok Cloud API
                final_anpr_plate = get_highest_frequency_plate(self._cam1_statuses)
            else:
                final_anpr_plate = "NO_PLATE_DETECTED"

            last_cam1_image = self._cam1_frames[-1] if self._cam1_frames else None
            aux_copy: dict[int | str, bytes | None] = {
                k: v for k, v in self._auxiliary_images.items()
            }
            # Include secondary ANPR camera snapshots (e.g. Rear ANPR Cam 2) in auxiliary images
            # so they get spooled into local SQLite spool_images
            for sec_idx, sec_img in self._secondary_anpr_images.items():
                if sec_img:
                    aux_copy[f"anpr_{sec_idx}"] = sec_img

            total_samples = len(self._cam1_plates)
            total_frames = len(self._cam1_frames)

            package = {
                "session_id": self.session_id,
                "weight": round(self.stable_weight, 3),
                "anpr_plate": final_anpr_plate,
                "cam1_final_image": last_cam1_image,
                "auxiliary_images": aux_copy,
                "total_anpr_samples": total_samples,
                "total_cam1_frames": total_frames,
                "timestamp": time.time(),
            }

            # Immediately release intermediate frame buffers from RAM
            self._cam1_frames.clear()
            self._auxiliary_images.clear()
            self._secondary_anpr_images.clear()

            logger.info(
                f"[Session {self.session_id}] Package finalized: "
                f"Plate='{final_anpr_plate}', Weight={self.stable_weight:.3f} kg, "
                f"Cam1 Frames={total_frames}, Aux Cams={len(aux_copy)}"
            )
            is_err = bool(not self._cam1_plates)
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
            self._aux_thread = None
            self.phase = SessionPhase.PHASE_IDLE
            self.session_id = None
            self.stable_weight = 0.0
            self._cam1_frames.clear()
            self._cam1_plates.clear()
            self._cam1_statuses.clear()
            self._auxiliary_images.clear()
            self._secondary_anpr_images.clear()

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
