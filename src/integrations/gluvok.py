"""
gluvok.py — Gluvok Cloud API Integration Client
===============================================
Handles stateless IoT device authentication, Indian vehicle plate sanitization,
RFC 2397 base64 payload construction, and POST transmission to Gluvok API (/api/entries).
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

import requests

from src.config.config_manager import config
from src.config.constants import (
    CLOUD_POST_TIMEOUT,
    GLUVOK_BASE_URL,
    INDIAN_PLATE_REGEX,
)
from src.core.telemetry import record_error_event, record_system_event

logger = logging.getLogger(__name__)


def get_device_headers() -> dict[str, str]:
    """
    Returns custom authentication headers required for edge device requests.
    - x-device-id: Integer primary key from the devices table
    - x-device-key: Raw pre-shared key
    """
    return {
        "x-device-id": str(config.device_id),
        "x-device-key": config.device_key,
    }


def sanitize_vehicle_number(raw_plate: str) -> tuple[str, str]:
    """
    Returns tuple of (detected_vehicle_number, vehicle_number).
    Ensures vehicle_number complies with Indian plate format for API validation.
    """
    raw = str(raw_plate or "UNKNOWN_PLATE").strip().upper()
    cleaned = re.sub(r"[^A-Z0-9]", "", raw)

    if INDIAN_PLATE_REGEX.match(cleaned):
        return raw, cleaned

    # Fallback formatting if raw is close to valid
    if len(cleaned) >= 8 and cleaned[:2].isalpha():
        return raw, cleaned

    # If raw plate was unreadable or failed OCR, send raw as detected and fallback format as vehicle_number
    fallback_plate = "MH00XX0000"
    return raw, fallback_plate


def _build_entry_payload(session_payload: dict[str, Any]) -> dict[str, Any]:
    """Builds the API entry payload with base64 images list from session dictionary."""
    images_list: list[str] = []
    weight_val = float(session_payload.get("weight", 0.0))
    raw_plate = str(session_payload.get("anpr_plate", "NO_PLATE_DETECTED"))
    detected_plate, _ = sanitize_vehicle_number(raw_plate)

    cam1_bytes = session_payload.get("cam1_final_image")
    if cam1_bytes:
        b64_str = base64.b64encode(cam1_bytes).decode("utf-8")
        images_list.append(f"data:image/jpeg;base64,{b64_str}")

    aux_images = session_payload.get("auxiliary_images", {})
    if isinstance(aux_images, dict):
        for cam_idx in sorted(aux_images.keys()):
            img_bytes = aux_images[cam_idx]
            if img_bytes:
                b64_aux = base64.b64encode(img_bytes).decode("utf-8")
                images_list.append(f"data:image/jpeg;base64,{b64_aux}")

    return {
        "detected_vehicle_number": detected_plate,
        "weight": round(weight_val, 3),
        "center_id": config.center_id,
        "images": images_list,
    }


def _record_cloud_event(event_type: str, message: str, is_error: bool = False) -> None:
    """Safely logs system and error events to the core telemetry store."""
    if is_error:
        record_error_event(event_type, message)
        record_system_event("CLOUD", f"Upload error ({event_type}): {message}")
    else:
        record_system_event(event_type, message)


def _handle_success_response(response: requests.Response, payload: dict[str, Any]) -> None:
    """Log and record telemetry for a successful entry creation."""
    res_data = response.json() if response.content else {}
    entry_id = res_data.get("data", {}).get("id", "N/A")
    logger.info(
        f"[Gluvok API] Entry created successfully! Entry ID: {entry_id} (HTTP {response.status_code})"
    )
    _record_cloud_event(
        "CLOUD",
        f"Entry #{entry_id} created: {payload.get('detected_vehicle_number')} @ {payload.get('weight')} kg",
    )


def _handle_error_status(status_code: int, response_text: str) -> None:
    """Log and record telemetry for non-success HTTP statuses."""
    error_events: dict[int, tuple[str, str, str]] = {
        401: (
            "[Gluvok API] 401 Unauthorized: Missing or invalid device authentication headers.",
            "CLOUD_AUTH_FAILED",
            "401 Unauthorized: Missing device authentication headers",
        ),
        403: (
            "[Gluvok API] 403 Forbidden: Invalid device key, device not found, or device deactivated.",
            "CLOUD_AUTH_FORBIDDEN",
            "403 Forbidden: Invalid device key, not found, or deactivated",
        ),
        400: (
            f"[Gluvok API] 400 Bad Request: Validation failed: {response_text}",
            "CLOUD_VALIDATION_ERROR",
            f"400 Bad Request: {response_text}",
        ),
    }
    if status_code in error_events:
        log_msg, event_type, event_msg = error_events[status_code]
    else:
        log_msg = f"[Gluvok API] POST /api/entries failed HTTP {status_code}: {response_text}"
        event_type = "CLOUD_UPLOAD_ERROR"
        event_msg = f"HTTP {status_code}"
    logger.error(log_msg)
    _record_cloud_event(event_type, event_msg, is_error=True)


def _handle_response_status(response: requests.Response, payload: dict[str, Any]) -> None:
    """Evaluates HTTP response status code and logs telemetry events."""
    if response.status_code in (200, 201):
        _handle_success_response(response, payload)
        return
    _handle_error_status(response.status_code, response.text)


def post_to_cloud(session_payload: dict[str, Any]) -> None:
    """
    Submits vehicle weighment session to Gluvok API (/api/entries).
    Authenticates statelessly via custom headers (x-device-id, x-device-key).
    """
    if not config.device_id or not config.device_key:
        logger.warning(
            "[Gluvok API] POST entry aborted: Device credentials (device_id, device_key) not configured."
        )
        _record_cloud_event(
            "CLOUD_AUTH_FAILED",
            "Device credentials not configured in config.json",
            is_error=True,
        )
        return

    entries_url = f"{GLUVOK_BASE_URL}/api/entries"
    logger.info(f"[Gluvok API] Transmitting weighment entry to: {entries_url}")

    payload = _build_entry_payload(session_payload)

    logger.info(
        f"[Gluvok API] Transmitting payload: Detected Vehicle='{payload.get('detected_vehicle_number')}', "
        f"Weight={payload['weight']} kg, Center ID={payload['center_id']}, Images={len(payload['images'])}"
    )

    headers = {
        "Content-Type": "application/json",
        "Connection": "close",
        **get_device_headers(),
    }

    try:
        response = requests.post(entries_url, json=payload, headers=headers, timeout=CLOUD_POST_TIMEOUT)
        _handle_response_status(response, payload)
    except (requests.RequestException, ValueError, KeyError) as e:
        logger.error(f"[Gluvok API] Network exception during entry transmission: {e}")
        _record_cloud_event("CLOUD_UPLOAD_ERROR", str(e), is_error=True)
    finally:
        session_payload.clear()


__all__ = [
    "GLUVOK_BASE_URL",
    "_build_entry_payload",
    "get_device_headers",
    "post_to_cloud",
    "sanitize_vehicle_number",
]
