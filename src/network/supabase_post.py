import base64
import logging
import re
from typing import Any

import requests

from src.config.config_manager import config
from src.network.supabase_auth import ensure_valid_auth, refresh_gluvok_token
from src.network.supabase_client import GLUVOK_BASE_URL, auth_state

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


def post_to_supabase(session_payload: float | dict[str, Any], is_retry: bool = False):
    """
    Submits vehicle weighment session to Gluvok API (/api/entries).
    Handles Bearer token auth, dynamic token refresh on 401, and direct Base64 image payloads.
    """
    if not ensure_valid_auth():
        logger.warning("[Gluvok API] POST entry aborted: Authentication failed.")
        return

    entries_url = f"{GLUVOK_BASE_URL}/api/entries"
    logger.info(f"[Gluvok API] Transmitting weighment entry to: {entries_url}")

    images_list: list[str] = []

    if isinstance(session_payload, dict):
        weight_val = float(session_payload.get("weight", 0.0))
        raw_plate = str(session_payload.get("anpr_plate", "NO_PLATE_DETECTED"))
        detected_plate, _ = sanitize_vehicle_number(raw_plate)

        # 1. Primary Camera 1 image (Data URI)
        cam1_bytes = session_payload.get("cam1_final_image")
        if cam1_bytes:
            b64_str = base64.b64encode(cam1_bytes).decode("utf-8")
            images_list.append(f"data:image/jpeg;base64,{b64_str}")

        # 2. Auxiliary overview camera images (Data URIs)
        aux_images = session_payload.get("auxiliary_images", {})
        if isinstance(aux_images, dict):
            for cam_idx in sorted(aux_images.keys()):
                img_bytes = aux_images[cam_idx]
                if img_bytes:
                    b64_aux = base64.b64encode(img_bytes).decode("utf-8")
                    images_list.append(f"data:image/jpeg;base64,{b64_aux}")

        payload = {
            "detected_vehicle_number": detected_plate,
            "weight": round(weight_val, 3),
            "center_id": config.supabase_center_id,
            "status": "pending",
            "images": images_list,
        }
    else:
        weight_val = float(session_payload)
        payload = {
            "detected_vehicle_number": "NO_PLATE_DETECTED",
            "weight": round(weight_val, 3),
            "center_id": config.supabase_center_id,
            "status": "pending",
            "images": [],
        }

    logger.info(
        f"[Gluvok API] Transmitting payload: Detected Vehicle='{payload.get('detected_vehicle_number')}', "
        f"Weight={payload['weight']} kg, Center ID={payload['center_id']}, Images={len(payload['images'])}"
    )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_state.access_token}",
        "Connection": "close"
    }

    try:
        response = requests.post(entries_url, json=payload, headers=headers, timeout=20)
        if response.status_code in (200, 201):
            res_data = response.json() if response.content else {}
            entry_id = res_data.get("data", {}).get("id", "N/A")
            logger.info(f"[Gluvok API] Entry created successfully! Entry ID: {entry_id} (HTTP {response.status_code})")
            try:
                from src.web.server import record_system_event
                record_system_event(
                    "CLOUD",
                    f"Entry #{entry_id} created: {payload.get('detected_vehicle_number')} @ {payload['weight']} kg"
                )
            except (ImportError, AttributeError):
                pass
        elif response.status_code == 401 and not is_retry:
            logger.warning("[Gluvok API] Access token expired (401). Refreshing token and retrying entry POST...")
            if refresh_gluvok_token():
                post_to_supabase(session_payload, is_retry=True)
            else:
                logger.error("[Gluvok API] Token refresh failed on 401 response.")
                try:
                    from src.web.server import record_error_event, record_system_event
                    record_error_event("CLOUD_AUTH_FAILED", "Token refresh failed")
                    record_system_event("CLOUD", "Cloud access token refresh failed.")
                except (ImportError, AttributeError):
                    pass
        else:
            logger.error(f"[Gluvok API] POST /api/entries failed HTTP {response.status_code}: {response.text}")
            try:
                from src.web.server import record_error_event, record_system_event
                record_error_event("CLOUD_UPLOAD_ERROR", f"HTTP {response.status_code}")
                record_system_event("CLOUD", f"Gluvok API entry POST failed: HTTP {response.status_code}")
            except (ImportError, AttributeError):
                pass
    except (requests.RequestException, ValueError, KeyError) as e:
        logger.error(f"[Gluvok API] Network exception during entry transmission: {e}")
        try:
            from src.web.server import record_error_event, record_system_event
            record_error_event("CLOUD_UPLOAD_ERROR", str(e))
            record_system_event("CLOUD", f"Gluvok API POST exception: {e}")
        except (ImportError, AttributeError):
            pass
    finally:
        # Clear base64 image strings from RAM immediately
        if isinstance(session_payload, dict):
            session_payload.clear()
        payload.clear()
        images_list.clear()
