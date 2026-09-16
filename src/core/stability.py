"""
stability.py — Scale Weight Stability & Session Trigger Machine
==============================================================
Weight session state machine with 10-second continuous stability detection.
Integrates with WeighbridgeSessionManager for camera captures and ANPR processing.
One transmission per session; resets only when weight returns to zero.
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any

from src.config.config_manager import config
from src.config.constants import STABILITY_DURATION, STABILITY_TOLERANCE
from src.core.session import session_manager

logger = logging.getLogger(__name__)


class ScaleState(Enum):
    SCALE_IDLE = 0
    SCALE_STABILIZING = 1
    SCALE_STABLE_RECORDED = 2


class ScaleStabilityMachine:
    def __init__(self):
        self.state = ScaleState.SCALE_IDLE
        self.last_weight = 0.0
        self._current_stable_candidate = 0.0
        self._candidate_start_time = 0.0
        self._last_printed_weight = -9999.0

    def _reset_candidate_state(self):
        self.state = ScaleState.SCALE_IDLE
        self._current_stable_candidate = 0.0
        self._candidate_start_time = 0.0

    def _log_weight_change(self, parsed_weight: float):
        if abs(parsed_weight - self._last_printed_weight) >= 0.1:
            logger.info(
                f"[Scale] Parsed weight: {parsed_weight:.3f} "
                f"(Threshold: {config.weight_threshold:.1f})"
            )
            self._last_printed_weight = parsed_weight

    def _handle_zero_or_subthreshold(self, parsed_weight: float) -> bool:
        if parsed_weight <= 0.0:
            if self.state != ScaleState.SCALE_IDLE:
                logger.info(
                    "[Scale Session] Weight returned to zero. "
                    "Session closed. Ready for next weighing."
                )
                self._reset_candidate_state()
                session_manager.reset_session()
            return True

        if parsed_weight < config.weight_threshold:
            self._reset_candidate_state()
            session_manager.reset_session()
            return True

        return False

    def _evaluate_stability_window(self, parsed_weight: float, now: float):
        if abs(parsed_weight - self._current_stable_candidate) <= STABILITY_TOLERANCE:
            elapsed = now - self._candidate_start_time
            if elapsed >= STABILITY_DURATION:
                logger.info(
                    f"[Scale Session] Stable weight confirmed (10s): "
                    f"{self._current_stable_candidate:.3f} kg. Triggering auxiliary cameras..."
                )
                self.state = ScaleState.SCALE_STABLE_RECORDED
                session_manager.on_weight_stabilized(self._current_stable_candidate)
        else:
            logger.debug(
                f"[Scale] Weight shifted from {self._current_stable_candidate:.3f} "
                f"to {parsed_weight:.3f}. Resetting stability timer."
            )
            self._current_stable_candidate = parsed_weight
            self._candidate_start_time = now

    def process_new_weight(self, parsed_weight: float):
        now = time.time()
        self.last_weight = parsed_weight
        self._log_weight_change(parsed_weight)

        completed_package = session_manager.check_session_progress()
        if completed_package:
            self._trigger_upload(completed_package)

        if self._handle_zero_or_subthreshold(parsed_weight):
            return

        if self.state == ScaleState.SCALE_STABLE_RECORDED:
            return

        if self.state == ScaleState.SCALE_IDLE:
            self.state = ScaleState.SCALE_STABILIZING
            self._current_stable_candidate = parsed_weight
            self._candidate_start_time = now
            session_manager.start_session()
            return

        self._evaluate_stability_window(parsed_weight, now)

    def _trigger_upload(self, session_package: dict[str, Any]) -> threading.Thread:
        from src.integrations.gluvok import post_to_cloud

        session_id = str(session_package.get("session_id", "unknown"))
        upload_thread = threading.Thread(
            target=post_to_cloud,
            args=(session_package,),
            name=f"CloudUpload_{session_id}",
            daemon=True,
        )
        upload_thread.start()
        logger.info(
            f"[Scale Session] Dispatched cloud upload for session {session_id} in background thread."
        )
        return upload_thread

    def reset(self):
        """Manually reset the state machine."""
        self.state = ScaleState.SCALE_IDLE
        self.last_weight = 0.0
        self._current_stable_candidate = 0.0
        self._candidate_start_time = 0.0
        self._last_printed_weight = -9999.0
        session_manager.reset_session()


# Module-level singleton
scale_state_machine = ScaleStabilityMachine()


def process_new_weight(weight: float):
    """Convenience function used by scale driver."""
    scale_state_machine.process_new_weight(weight)


def get_scale_state() -> ScaleState:
    """Expose current state."""
    return scale_state_machine.state


def get_current_weight() -> float:
    return scale_state_machine.last_weight


__all__ = [
    "ScaleStabilityMachine",
    "ScaleState",
    "get_current_weight",
    "get_scale_state",
    "process_new_weight",
    "scale_state_machine",
]
