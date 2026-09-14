from __future__ import annotations

import base64
import logging
import re
from typing import Any

import requests

from src.config.config_manager import config
from src.network.cloud_client import GLUVOK_BASE_URL, get_device_headers

logger = logging.getLogger(__name__)

# Pattern for Indian vehicle registration numbers (e.g. MH12AB1234, DL1CAB1234, 22BH1234AA)
INDIAN_PLATE_REGEX = re.compile(
    r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$|^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$"
)


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
    """Safely logs system and error events to the diagnostics web store."""
    try:
        from src.web.server import record_error_event, record_system_event

        if is_error:
            record_error_event(event_type, message)
            record_system_event("CLOUD", f"Upload error ({event_type}): {message}")
        else:
            record_system_event(event_type, message)
    except (ImportError, AttributeError):
        pass


def _handle_response_status(response: requests.Response, payload: dict[str, Any]) -> None:
    """Evaluates HTTP response status code and logs telemetry events."""
    if response.status_code in (200, 201):
        res_data = response.json() if response.content else {}
        entry_id = res_data.get("data", {}).get("id", "N/A")
        logger.info(
            f"[Gluvok API] Entry created successfully! Entry ID: {entry_id} (HTTP {response.status_code})"
        )
        _record_cloud_event(
            "CLOUD",
            f"Entry #{entry_id} created: {payload.get('detected_vehicle_number')} @ {payload.get('weight')} kg",
        )
    elif response.status_code == 401:
        logger.error(
            "[Gluvok API] 401 Unauthorized: Missing or invalid device authentication headers."
        )
        _record_cloud_event(
            "CLOUD_AUTH_FAILED",
            "401 Unauthorized: Missing device authentication headers",
            is_error=True,
        )
    elif response.status_code == 403:
        logger.error(
            "[Gluvok API] 403 Forbidden: Invalid device key, device not found, or device deactivated."
        )
        _record_cloud_event(
            "CLOUD_AUTH_FORBIDDEN",
            "403 Forbidden: Invalid device key, not found, or deactivated",
            is_error=True,
        )
    elif response.status_code == 400:
        logger.error(f"[Gluvok API] 400 Bad Request: Validation failed: {response.text}")
        _record_cloud_event(
            "CLOUD_VALIDATION_ERROR",
            f"400 Bad Request: {response.text}",
            is_error=True,
        )
    else:
        logger.error(f"[Gluvok API] POST /api/entries failed HTTP {response.status_code}: {response.text}")
        _record_cloud_event(
            "CLOUD_UPLOAD_ERROR",
            f"HTTP {response.status_code}",
            is_error=True,
        )


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
        response = requests.post(entries_url, json=payload, headers=headers, timeout=20)
        _handle_response_status(response, payload)
    except (requests.RequestException, ValueError, KeyError) as e:
        logger.error(f"[Gluvok API] Network exception during entry transmission: {e}")
        _record_cloud_event("CLOUD_UPLOAD_ERROR", str(e), is_error=True)
    finally:
        session_payload.clear()
