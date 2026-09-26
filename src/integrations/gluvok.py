"""
gluvok.py — Gluvok Cloud API Integration Client
===============================================
Handles HTTP Basic Authentication (-u device_id:device_key), multipart/form-data
weighment transmission matching the official curl specification, and anti-duplicate
verification against Gluvok API (/api/entries).
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from src.config import config
from src.config.constants import CLOUD_POST_TIMEOUT, GLUVOK_BASE_URL
from src.core.telemetry import record_error_event, record_system_event
from src.services.image_compressor import compress_image_bytes

logger = logging.getLogger(__name__)


def _record_cloud_event(event_type: str, message: str, is_error: bool = False) -> None:
    """Safely logs system and error events to the core telemetry store."""
    if is_error:
        record_error_event(event_type, message)
        record_system_event("CLOUD", f"Upload error ({event_type}): {message}")
    else:
        record_system_event(event_type, message)


def _build_multipart_files(
    images: list[tuple[str, bytes]] | None,
    image_bytes: bytes | None,
    filename: str,
) -> tuple[list[tuple[str, tuple[str, bytes, str]]], bool]:
    valid_images: list[tuple[str, bytes]] = []
    if images:
        for fname, b in images:
            if b and isinstance(b, bytes) and len(b) > 0:
                compressed = compress_image_bytes(b) or b
                valid_images.append((fname, compressed))

    if not valid_images and image_bytes and isinstance(image_bytes, bytes) and len(image_bytes) > 0:
        compressed = compress_image_bytes(image_bytes) or image_bytes
        valid_images.append((filename, compressed))

    if valid_images:
        files: list[tuple[str, tuple[str, bytes, str]]] = [
            ("file", (fn, b, "image/jpeg")) for fn, b in valid_images
        ]
        return files, True
    return [("file", (filename, b"", "image/jpeg"))], False


def _parse_cloud_response(
    response: requests.Response, safe_plate: str, weight: float
) -> tuple[bool, str | None, str | None, bool]:
    if response.status_code in (200, 201):
        res_data = response.json() if response.content else {}
        entry_id = str(res_data.get("data", {}).get("id") or res_data.get("id") or "N/A")
        logger.info(f"[Gluvok API] Entry #{entry_id} created successfully (HTTP {response.status_code})")
        _record_cloud_event("CLOUD", f"Entry #{entry_id} created: {safe_plate} @ {weight:.3f} kg")
        return True, entry_id, None, False

    if response.status_code == 409:
        res_data = response.json() if response.content else {}
        entry_id = str(res_data.get("data", {}).get("id") or res_data.get("id") or "EXISTING")
        logger.info(f"[Gluvok API] Entry already acknowledged (HTTP 409 Conflict). ID: {entry_id}")
        _record_cloud_event("CLOUD", f"Entry already exists in cloud: {safe_plate}")
        return True, entry_id, None, False

    err_msg = f"HTTP {response.status_code}: {response.text}"
    event_map = {
        401: "CLOUD_AUTH_FAILED",
        403: "CLOUD_AUTH_FORBIDDEN",
        400: "CLOUD_VALIDATION_ERROR",
    }
    event_type = event_map.get(response.status_code, "CLOUD_UPLOAD_ERROR")
    _record_cloud_event(event_type, err_msg, is_error=True)
    logger.error(f"[Gluvok API] POST /api/entries failed {err_msg}")
    return False, None, err_msg, False


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
        -F "file=@/home/pi/captures/truck_anpr_1.jpg;type=image/jpeg" \\
        -F "file=@/home/pi/captures/truck_aux_2.jpg;type=image/jpeg" ...
    """
    if not config.device_id or not config.device_key:
        msg = "Device credentials (device_id, device_key) not configured."
        logger.warning(f"[Gluvok API] POST entry aborted: {msg}")
        _record_cloud_event("CLOUD_AUTH_FAILED", msg, is_error=True)
        return False, None, msg, False

    entries_url = f"{GLUVOK_BASE_URL}/api/entries"
    auth = (str(config.device_id), config.device_key)
    raw_plate = str(detected_vehicle_number or "NO_PLATE_DETECTED").strip().upper()
    safe_plate = (
        "NO_PLATE_DETECTED"
        if not raw_plate or raw_plate in ("UNKNOWN_PLATE", "UNKNOWN", "NONE", "NULL", "SUCCESS")
        else raw_plate
    )
    data = {
        "center_id": str(center_id),
        "detected_vehicle_number": safe_plate,
        "weight": str(round(weight, 3)),
    }
    files, has_images = _build_multipart_files(images, image_bytes, filename)

    logger.info(
        f"[Gluvok API] Transmitting multipart entry to {entries_url}: "
        f"Vehicle='{safe_plate}', Weight={weight:.3f} kg, Center ID={center_id}"
    )

    try:
        response = requests.post(
            entries_url, auth=auth, data=data, files=files, timeout=CLOUD_POST_TIMEOUT
        )
        if response.status_code == 400 and has_images and "storage" in response.text.lower():
            logger.warning(
                "[Gluvok API] Storage failed on remote server. Retrying without image payload..."
            )
            fallback_files = [("file", (filename, b"", "image/jpeg"))]
            response = requests.post(
                entries_url, auth=auth, data=data, files=fallback_files, timeout=CLOUD_POST_TIMEOUT
            )
        return _parse_cloud_response(response, safe_plate, weight)

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
    raw_plate = str(detected_vehicle_number or "NO_PLATE_DETECTED").strip().upper()
    safe_plate = (
        "NO_PLATE_DETECTED"
        if not raw_plate or raw_plate in ("UNKNOWN_PLATE", "UNKNOWN", "NONE", "NULL", "SUCCESS")
        else raw_plate
    )
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
    raw_plate = str(session_payload.get("anpr_plate", "NO_PLATE_DETECTED")).strip().upper()
    plate = (
        "NO_PLATE_DETECTED"
        if not raw_plate or raw_plate in ("UNKNOWN_PLATE", "UNKNOWN", "NONE", "NULL", "SUCCESS")
        else raw_plate
    )
    weight = float(session_payload.get("weight", 0.0))

    images_to_send: list[tuple[str, bytes]] = []
    fleet_dict = session_payload.get("camera_snapshots", {})
    if isinstance(fleet_dict, dict):
        for cam_name in sorted(fleet_dict.keys()):
            b = fleet_dict[cam_name]
            if b and isinstance(b, bytes):
                images_to_send.append((f"truck_{cam_name}.jpg", b))

    transmit_entry_multipart(
        center_id=center_id,
        detected_vehicle_number=plate,
        weight=weight,
        images=images_to_send,
    )


__all__ = [
    "GLUVOK_BASE_URL",
    "post_to_cloud",
    "transmit_entry_multipart",
    "verify_entry_in_cloud",
]
