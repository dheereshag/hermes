from __future__ import annotations

import re
from typing import Any

VALID_BAUD_RATES = {300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200}
SERIAL_PORT_PATTERN = re.compile(r"^[a-zA-Z0-9_\-/\.]{1,64}$")


def is_valid_url(url: str, allowed_schemes: tuple[str, ...] = ("http://", "https://", "rtsp://")) -> bool:
    """Validates that a URL string starts with allowed schemes and contains no illegal characters."""
    if not url:
        return True
    u_lower = url.lower()
    if not u_lower.startswith(allowed_schemes):
        return False
    return not any(c in url for c in ("\r", "\n", "\0", " "))


def _validate_weight_threshold(val: Any) -> tuple[bool, str | None]:
    if val is None:
        return True, None
    try:
        w = float(val)
        if w < 0.0 or w > 100000.0:
            return False, "Threshold weight must be between 0 and 100,000 kg."
        return True, None
    except (ValueError, TypeError):
        return False, "Invalid threshold weight value."


def _validate_serial_settings(port: Any, baud: Any) -> tuple[bool, str | None]:
    if baud is not None:
        try:
            if int(baud) not in VALID_BAUD_RATES:
                return False, "Invalid baud rate value."
        except (ValueError, TypeError):
            return False, "Invalid baud rate value."

    if port is not None:
        sp_str = str(port).strip()
        if sp_str and not SERIAL_PORT_PATTERN.match(sp_str):
            return False, "Invalid serial port path character set."

    return True, None


def _validate_camera_urls(
    anpr_cam: Any,
    aux_cams: Any,
    anpr_server: Any,
) -> tuple[bool, str | None]:
    if anpr_cam is not None and not is_valid_url(str(anpr_cam)):
        return False, "ANPR Camera URL must start with http://, https://, or rtsp://"

    if anpr_server is not None and not is_valid_url(str(anpr_server), allowed_schemes=("http://", "https://")):
        return False, "ANPR Server URL must start with http:// or https://"

    if aux_cams is not None:
        if not isinstance(aux_cams, list):
            return False, "Auxiliary camera URLs must be a list."
        for u in aux_cams:
            if not is_valid_url(str(u)):
                return False, f"Invalid auxiliary camera URL: {u}"

    return True, None


def validate_config_payload(data: dict[str, Any]) -> tuple[bool, str | None]:
    """Validates configuration parameters from JSON payload with guard clauses."""
    valid_wt, err_wt = _validate_weight_threshold(data.get("min_weight"))
    if not valid_wt:
        return False, err_wt

    valid_serial, err_serial = _validate_serial_settings(
        data.get("serial_port"),
        data.get("serial_baudrate"),
    )
    if not valid_serial:
        return False, err_serial

    valid_cams, err_cams = _validate_camera_urls(
        data.get("anpr_camera_url"),
        data.get("auxiliary_camera_urls"),
        data.get("anpr_server_url"),
    )
    if not valid_cams:
        return False, err_cams

    return True, None
