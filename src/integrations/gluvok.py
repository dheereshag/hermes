"""
gluvok.py — Gluvok Cloud API Integration Client
===============================================
Handles HTTP Basic Authentication (-u device_id:device_key), multipart/form-data
weighment transmission matching the official curl specification, and anti-duplicate
verification against Gluvok API (/api/entries).
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

from src.config import config
from src.config.constants import (
    CLOUD_POST_TIMEOUT,
    GLUVOK_BASE_URL,
    INDIAN_PLATE_REGEX,
)
from src.core.telemetry import record_error_event, record_system_event

logger = logging.getLogger(__name__)


def get_device_headers() -> dict[str, str]:
    """
    Returns custom authentication headers if required by specific endpoints.
    - x-device-id: Identifier from devices table
    - x-device-key: Pre-shared key
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
    raw = str(raw_plate or "").strip().upper()
    cleaned = re.sub(r"[^A-Z0-9]", "", raw)

    if INDIAN_PLATE_REGEX.match(cleaned):
        return cleaned, cleaned

    # If raw plate was unreadable or does not match regex, fallback to valid placeholder format
    fallback_plate = "MH00XX0000"
    return fallback_plate, fallback_plate


def _record_cloud_event(event_type: str, message: str, is_error: bool = False) -> None:
    """Safely logs system and error events to the core telemetry store."""
    if is_error:
        record_error_event(event_type, message)
        record_system_event("CLOUD", f"Upload error ({event_type}): {message}")
    else:
        record_system_event(event_type, message)


def transmit_entry_multipart(
    center_id: int,
    detected_vehicle_number: str,
    weight: float,
    image_bytes: bytes | None = None,
    filename: str = "truck_001.jpg",
    images: list[tuple[str, bytes]] | None = None,
) -> tuple[bool, str | None, str | None, bool]:
    """
    Submits vehicle weighment session to Gluvok API (/api/entries) matching the curl specification:
      curl -X POST "https://gluvok.vercel.app/api/entries" \\
        -u "pi1:hardware123" \\
        -F "center_id=1" \\
        -F "detected_vehicle_number=MH12AB1234" \\
        -F "weight=18540.5" \\
        -F "file=@/home/pi/captures/truck_cam1.jpg;type=image/jpeg" \\
        -F "file=@/home/pi/captures/truck_aux_2.jpg;type=image/jpeg" ...

    Supports transmitting all connected camera images (ANPR + Auxiliary overview cameras).

    Returns:
        (success: bool, entry_id: str | None, error_message: str | None, is_read_timeout: bool)
    """
    if not config.device_id or not config.device_key:
        msg = "Device credentials (device_id, device_key) not configured."
        logger.warning(f"[Gluvok API] POST entry aborted: {msg}")
        _record_cloud_event("CLOUD_AUTH_FAILED", msg, is_error=True)
        return False, None, msg, False

    entries_url = f"{GLUVOK_BASE_URL}/api/entries"
    auth = (str(config.device_id), config.device_key)

    _, safe_plate = sanitize_vehicle_number(detected_vehicle_number)

    data = {
        "center_id": str(center_id),
        "detected_vehicle_number": safe_plate,
        "weight": str(round(weight, 3)),
    }

    # Collect valid images from images list or single image_bytes
    valid_images: list[tuple[str, bytes]] = []
    if images:
        for fname, b in images:
            if b and isinstance(b, bytes) and len(b) > 0:
                valid_images.append((fname, b))

    if not valid_images and image_bytes and isinstance(image_bytes, bytes) and len(image_bytes) > 0:
        valid_images.append((filename, image_bytes))

    # In curl -F, multipart/form-data is always used. In requests, passing files
    # forces multipart/form-data encoding with boundary even if image is not present.
    if valid_images:
        files: list[tuple[str, tuple[str, bytes, str]]] = [
            ("file", (fn, b, "image/jpeg")) for fn, b in valid_images
        ]
    else:
        files = [("file", (filename, b"", "image/jpeg"))]

    logger.info(
        f"[Gluvok API] Transmitting multipart entry to {entries_url}: "
        f"Vehicle='{safe_plate}', Weight={weight:.3f} kg, Center ID={center_id}, Images={len(valid_images)}"
    )

    try:
        response = requests.post(
            entries_url,
            auth=auth,
            data=data,
            files=files,
            timeout=CLOUD_POST_TIMEOUT,
        )

        # If remote cloud storage bucket upload failed (e.g. Supabase bucket misconfiguration),
        # retry with empty file payload so the weighment record is safely saved to the cloud DB.
        if response.status_code == 400 and valid_images and "storage" in response.text.lower():
            logger.warning(
                "[Gluvok API] Cloud storage bucket failed on remote server. "
                "Retrying without image payload to guarantee weighment entry is saved..."
            )
            fallback_files = [("file", (filename, b"", "image/jpeg"))]
            response = requests.post(
                entries_url,
                auth=auth,
                data=data,
                files=fallback_files,
                timeout=CLOUD_POST_TIMEOUT,
            )

        # 200 OK / 201 Created
        if response.status_code in (200, 201):
            res_data = response.json() if response.content else {}
            entry_id = str(res_data.get("data", {}).get("id") or res_data.get("id") or "N/A")
            logger.info(f"[Gluvok API] Entry #{entry_id} created successfully (HTTP {response.status_code})")
            _record_cloud_event(
                "CLOUD",
                f"Entry #{entry_id} created: {safe_plate} @ {weight:.3f} kg",
            )
            return True, entry_id, None, False

        # 409 Conflict: Already exists / idempotent duplicate acknowledgement
        if response.status_code == 409:
            res_data = response.json() if response.content else {}
            entry_id = str(res_data.get("data", {}).get("id") or res_data.get("id") or "EXISTING")
            logger.info(f"[Gluvok API] Entry already acknowledged by cloud (HTTP 409 Conflict). ID: {entry_id}")
            _record_cloud_event("CLOUD", f"Entry already exists in cloud: {detected_vehicle_number}")
            return True, entry_id, None, False

        # Error status handling
        err_msg = f"HTTP {response.status_code}: {response.text}"
        if response.status_code == 401:
            _record_cloud_event("CLOUD_AUTH_FAILED", err_msg, is_error=True)
        elif response.status_code == 403:
            _record_cloud_event("CLOUD_AUTH_FORBIDDEN", err_msg, is_error=True)
        elif response.status_code == 400:
            _record_cloud_event("CLOUD_VALIDATION_ERROR", err_msg, is_error=True)
        else:
            _record_cloud_event("CLOUD_UPLOAD_ERROR", err_msg, is_error=True)


        logger.error(f"[Gluvok API] POST /api/entries failed {err_msg}")
        return False, None, err_msg, False

    except requests.exceptions.ReadTimeout as e:
        err_msg = f"ReadTimeout: {e}"
        logger.warning(f"[Gluvok API] Read timeout awaiting response from server: {err_msg}")
        _record_cloud_event("CLOUD_UPLOAD_ERROR", err_msg, is_error=True)
        return False, None, err_msg, True

    except (requests.RequestException, OSError, ValueError) as e:
        err_msg = f"{type(e).__name__}: {e}"
        logger.error(f"[Gluvok API] Network exception during transmission: {err_msg}")
        _record_cloud_event("CLOUD_UPLOAD_ERROR", err_msg, is_error=True)
        return False, None, err_msg, False


def verify_entry_in_cloud(
    center_id: int,
    detected_vehicle_number: str,
    weight: float,
) -> str | None:
    """
    Verifies if an entry with matching vehicle and weight exists in the cloud.
    Called specifically after an ambiguous ReadTimeout to prevent creating duplicate entries.
    """
    if not config.device_id or not config.device_key:
        return None

    entries_url = f"{GLUVOK_BASE_URL}/api/entries"
    auth = (str(config.device_id), config.device_key)
    _, safe_plate = sanitize_vehicle_number(detected_vehicle_number)
    params = {
        "center_id": str(center_id),
        "detected_vehicle_number": safe_plate,
    }

    try:
        response = requests.get(entries_url, auth=auth, params=params, timeout=10.0)
        if response.status_code == 200:
            res_data = response.json()
            entries = res_data.get("data", []) if isinstance(res_data, dict) else []
            if isinstance(entries, list):
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    entry_weight = float(entry.get("weight", 0.0))
                    # Check if weight matches within 2.0 kg tolerance
                    if abs(entry_weight - weight) <= 2.0:
                        entry_id = str(entry.get("id", "VERIFIED"))
                        logger.info(
                            f"[Gluvok API] Pre-retry verification found entry #{entry_id} in cloud. "
                            f"Duplicate upload prevented!"
                        )
                        return entry_id
    except (requests.RequestException, ValueError, KeyError) as e:
        logger.debug(f"[Gluvok API] Verification query returned error: {e}")

    return None


def post_to_cloud(session_payload: dict[str, Any]) -> None:
    """
    Bridge function: transmits entry from session dictionary and updates telemetry.
    Preserved for direct callers; does NOT wipe session_payload on completion.
    """
    center_id = int(config.center_id)
    raw_plate = str(session_payload.get("anpr_plate", "NO_PLATE_DETECTED"))
    detected_plate, _ = sanitize_vehicle_number(raw_plate)
    weight = float(session_payload.get("weight", 0.0))

    images_to_send: list[tuple[str, bytes]] = []
    cam1_bytes = session_payload.get("cam1_final_image")
    if cam1_bytes and isinstance(cam1_bytes, bytes):
        images_to_send.append(("truck_cam1.jpg", cam1_bytes))

    aux_dict = session_payload.get("auxiliary_images", {})
    if isinstance(aux_dict, dict):
        for idx, b in aux_dict.items():
            if b and isinstance(b, bytes):
                images_to_send.append((f"truck_aux_{idx}.jpg", b))

    if not images_to_send and "images" in session_payload:
        for idx, b in enumerate(session_payload["images"]):
            if b and isinstance(b, bytes):
                images_to_send.append((f"truck_{idx+1}.jpg", b))

    transmit_entry_multipart(
        center_id=center_id,
        detected_vehicle_number=detected_plate,
        weight=weight,
        images=images_to_send,
    )


__all__ = [
    "GLUVOK_BASE_URL",
    "get_device_headers",
    "post_to_cloud",
    "sanitize_vehicle_number",
    "transmit_entry_multipart",
    "verify_entry_in_cloud",
]
