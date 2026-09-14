from __future__ import annotations

import threading
import time
from typing import Any

_system_events: list[dict[str, str]] = []
_events_lock = threading.Lock()

_latest_weighment: dict[str, Any] = {
    "session_id": None,
    "plate": None,
    "weight": 0.0,
    "timestamp": None,
    "is_error": False,
    "status_code": "READY",
}
_error_counts: dict[str, int] = {}
_live_lock = threading.Lock()


def record_system_event(source: str, message: str) -> None:
    """Appends an event to the circular telemetry log (max 20 entries)."""
    with _events_lock:
        if len(_system_events) >= 20:
            _system_events.pop(0)
        _system_events.append({
            "time": time.strftime("%H:%M:%S"),
            "source": source,
            "message": message,
        })


def record_weighment_result(
    session_id: str,
    plate: str,
    weight: float,
    is_error: bool = False,
    status_code: str = "SUCCESS",
) -> None:
    """Records the latest weighbridge session outcome and updates live error counters."""
    with _live_lock:
        _latest_weighment["session_id"] = session_id
        _latest_weighment["plate"] = plate
        _latest_weighment["weight"] = weight
        _latest_weighment["timestamp"] = time.strftime("%H:%M:%S")
        _latest_weighment["is_error"] = is_error
        _latest_weighment["status_code"] = status_code

        if is_error or status_code not in ("SUCCESS", "READY"):
            _error_counts[status_code] = _error_counts.get(status_code, 0) + 1


def record_error_event(error_code: str, message: str = "") -> None:
    """Explicitly increments live occurrence count for a system error code."""
    with _live_lock:
        _error_counts[error_code] = _error_counts.get(error_code, 0) + 1


def get_latest_weighment() -> dict[str, Any]:
    """Returns a snapshot of the latest weighment status."""
    with _live_lock:
        return dict(_latest_weighment)


def get_error_counts() -> dict[str, int]:
    """Returns a snapshot of active error counts."""
    with _live_lock:
        return dict(_error_counts)


def get_system_events() -> list[dict[str, str]]:
    """Returns a copy of the circular telemetry event buffer."""
    with _events_lock:
        return list(_system_events)


def reset_state() -> None:
    """Resets in-memory telemetry buffers (useful for testing)."""
    with _events_lock:
        _system_events.clear()
    with _live_lock:
        _latest_weighment["session_id"] = None
        _latest_weighment["plate"] = None
        _latest_weighment["weight"] = 0.0
        _latest_weighment["timestamp"] = None
        _latest_weighment["is_error"] = False
        _latest_weighment["status_code"] = "READY"
        _error_counts.clear()
