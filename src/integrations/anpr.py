"""
anpr.py — Argus ANPR Microservice REST Client
=============================================
Sends raw JPEG frames to the Argus ANPR endpoint (/recognize), parses plate results,
and computes consensus vehicle plate numbers via frequency counting.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Sequence

import requests

from src.config.config_manager import config
from src.config.constants import ANPR_SERVER_TIMEOUT

logger = logging.getLogger(__name__)


def resolve_anpr_endpoint(url: str | None = None) -> str:
    """Resolves ANPR server URL, replacing 0.0.0.0 with 127.0.0.1 and appending /recognize if omitted."""
    raw = (url or config.anpr_server_url or "http://127.0.0.1:8000/recognize").strip()
    raw = raw.replace("://0.0.0.0", "://127.0.0.1")
    raw = raw.rstrip("/")
    if not raw.endswith("/recognize"):
        raw = f"{raw}/recognize"
    return raw


def _normalize_plate_value(plate_val: object) -> str | None:
    """Return a cleaned plate string, or None if the value is empty/N/A."""
    if not plate_val or not isinstance(plate_val, str):
        return None
    plate_clean = plate_val.strip().upper()
    if not plate_clean or plate_clean == "N/A":
        return None
    return plate_clean


def _plate_from_results_list(data: dict) -> tuple[str | None, str] | None:
    """Extract plate from Argus `results[]` list.

    If multiple vehicles are detected, the first vehicle (results[0]) is strictly considered.
    Returns (plate, "SUCCESS"), (None, "NO_PLATE_DETECTED"), or None if 'results' not in data.
    """
    if "results" not in data:
        return None

    results = data.get("results")
    if not isinstance(results, list) or len(results) == 0:
        return None, str(data.get("status", "NO_PLATE_DETECTED")).upper()

    first_item = results[0]
    if not isinstance(first_item, dict):
        return None, str(data.get("status", "NO_PLATE_DETECTED")).upper()

    plate_clean = _normalize_plate_value(first_item.get("plate"))
    if not plate_clean:
        logger.info("[ANPR] Primary vehicle (first in array) has no readable plate.")
        return None, str(data.get("status", "NO_PLATE_DETECTED")).upper()

    exec_time = data.get("execution_time_ms", "N/A")
    vtype = first_item.get("vehicle_type") or "vehicle"
    conf = first_item.get("confidence")
    conf_str = f", conf={conf:.4f}" if isinstance(conf, (int, float)) else ""
    multi_info = f" [selected vehicle 1 of {len(results)}]" if len(results) > 1 else ""

    logger.info(
        f"[ANPR] Argus recognized primary plate: '{plate_clean}' "
        f"({vtype}{conf_str}, {exec_time}ms{multi_info})"
    )
    return plate_clean, "SUCCESS"


def _plate_from_flat_keys(data: dict) -> tuple[str, str] | None:
    """Extract plate from flat JSON keys used by generic ANPR responses."""
    for key in ("plate", "number_plate", "plate_number", "text", "result"):
        plate_clean = _normalize_plate_value(data.get(key))
        if plate_clean:
            logger.info(f"[ANPR] Server returned plate: '{plate_clean}' (key='{key}')")
            return plate_clean, "SUCCESS"
    return None


def _extract_plate_from_dict(data: dict) -> tuple[str | None, str | None]:
    """Extract plate string or status code from Argus / generic JSON response."""
    raw_status = str(data.get("status", "NO_PLATE_DETECTED")).upper()
    if data.get("rejected"):
        status_msg = data.get("status_message", "Pre-screening rejected frame")
        logger.info(f"[ANPR] Argus pre-screening rejected frame: {status_msg} (status: {raw_status})")
        return None, raw_status

    if data.get("success") is False and not data.get("results"):
        status_msg = data.get("status_message", "No plate detected")
        logger.info(f"[ANPR] Argus reported: {status_msg} (status: {raw_status})")
        return None, raw_status

    from_results = _plate_from_results_list(data)
    if from_results is not None:
        return from_results

    from_flat = _plate_from_flat_keys(data)
    if from_flat is not None:
        return from_flat

    if "status" in data:
        return None, raw_status

    return None, "NO_PLATE_DETECTED"


def _parse_anpr_response(response: requests.Response) -> tuple[str | None, str]:
    """Parses HTTP response body from ANPR microservice."""
    if response.status_code in (200, 201):
        try:
            data = response.json()
            if isinstance(data, dict):
                logger.info(f"[Argus Response]\n{json.dumps(data, indent=2)}")
                plate, status = _extract_plate_from_dict(data)
                if status is not None:
                    return plate, status
            elif isinstance(data, str) and data.strip():
                logger.info(f"[Argus Response] '{data.strip()}'")
                return data.strip().upper(), "SUCCESS"
        except (ValueError, KeyError, json.JSONDecodeError, TypeError) as parse_err:
            text = response.text.strip().upper()
            if text and text != "N/A":
                logger.info(f"[ANPR] Server returned text response: '{text}'")
                return text, "SUCCESS"
            logger.warning(f"[ANPR] Failed to parse server response: {parse_err}")

    error_code = f"ANPR_HTTP_{response.status_code}"
    logger.warning(f"[ANPR] Server POST status {response.status_code}: {response.text[:120]}")
    return None, error_code


def send_frame_to_anpr_server(
    image_bytes: bytes | None,
    server_url: str | None = None,
    timeout: float = ANPR_SERVER_TIMEOUT,
) -> tuple[str | None, str]:
    """
    Sends raw JPEG image bytes to the Argus ANPR FastAPI microservice (/recognize).
    Returns a tuple of (plate_string | None, status_code).
    """
    if not image_bytes:
        return None, "EMPTY_IMAGE"

    target_url = resolve_anpr_endpoint(server_url)

    try:
        files = {"file": ("frame.jpg", image_bytes, "image/jpeg")}
        response = requests.post(target_url, files=files, timeout=timeout)
        return _parse_anpr_response(response)
    except requests.exceptions.Timeout:
        logger.warning(f"[ANPR] Timeout ({timeout}s) contacting ANPR server at {target_url}")
        return None, "ANPR_TIMEOUT"
    except requests.exceptions.ConnectionError:
        logger.warning(f"[ANPR] Failed to connect to ANPR server at {target_url}. Is Argus running?")
        return None, "ANPR_CONNECTION_ERROR"
    except requests.RequestException as e:
        logger.error(f"[ANPR] Exception submitting frame to ANPR server ({target_url}): {e}")
        return None, "ANPR_REQUEST_ERROR"


def get_highest_frequency_plate(plate_list: Sequence[str | None]) -> str:
    """
    Analyzes a list of plate reading strings collected during a session and returns
    the string with the highest frequency.
    Returns 'UNKNOWN_PLATE' if no valid plate was recognized.
    """
    valid_plates = [p.strip().upper() for p in plate_list if p and isinstance(p, str) and p.strip()]

    if not valid_plates:
        logger.warning("[ANPR Voting] No valid plates recorded during session.")
        return "UNKNOWN_PLATE"

    counter = Counter(valid_plates)
    most_common_plate, count = counter.most_common(1)[0]
    total_samples = len(valid_plates)

    logger.info(
        f"[ANPR Voting] Winner: '{most_common_plate}' "
        f"(Frequency: {count}/{total_samples}, All candidates: {dict(counter)})"
    )
    return most_common_plate


__all__ = [
    "get_highest_frequency_plate",
    "resolve_anpr_endpoint",
    "send_frame_to_anpr_server",
]
