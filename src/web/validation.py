"""validation.py — Request payload validation for web interface."""
from __future__ import annotations

import re
from typing import Any

VALID_BAUDRATES = {300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200}
SERIAL_PORT_PATTERN = re.compile(r"^[a-zA-Z0-9_\-/\.]{1,64}$")
IMMUTABLE_FIELDS = {"center_id", "min_weight", "anpr_server_url", "device_id", "device_key"}


def is_valid_url(url: str) -> bool:
    if not url:
        return True
    u = url.lower()
    return u.startswith(("http://", "https://", "rtsp://")) and not any(c in url for c in ("\r", "\n", "\0", " "))


def _validate_serial(port: Any, baud: Any) -> tuple[bool, str | None]:
    if baud is not None:
        try:
            if int(baud) not in VALID_BAUDRATES:
                return False, "Invalid baud rate value."
        except (ValueError, TypeError):
            return False, "Invalid baud rate value."
    if port is not None and not SERIAL_PORT_PATTERN.match(str(port).strip()):
        return False, "Invalid serial port path character set."
    return True, None


def _validate_cameras(urls: Any) -> tuple[bool, str | None]:
    if urls is not None:
        if not isinstance(urls, list):
            return False, "Camera URLs must be a list."
        for u in urls:
            if not is_valid_url(str(u)):
                return False, f"Invalid camera URL: {u}"
    return True, None


def _validate_stability(duration: Any, tolerance: Any) -> tuple[bool, str | None]:
    if duration is not None:
        try:
            if not (1.0 <= float(duration) <= 60.0):
                return False, "Stability duration must be between 1.0 and 60.0 seconds."
        except (ValueError, TypeError):
            return False, "Invalid stability duration value."
    if tolerance is not None:
        try:
            if not (0.1 <= float(tolerance) <= 50.0):
                return False, "Stability tolerance must be between 0.1 and 50.0 kg."
        except (ValueError, TypeError):
            return False, "Invalid stability tolerance value."
    return True, None


def validate_config_payload(data: dict[str, Any]) -> tuple[bool, str | None]:
    for key in IMMUTABLE_FIELDS:
        if key in data:
            return False, f"Field '{key}' is compiled into the binary and cannot be modified via UI."
    ok_serial, err_serial = _validate_serial(data.get("serial_port"), data.get("serial_baudrate"))
    if not ok_serial:
        return False, err_serial
    ok_stab, err_stab = _validate_stability(data.get("stability_duration"), data.get("stability_tolerance"))
    if not ok_stab:
        return False, err_stab
    for cam_field in ("anpr_camera_urls", "auxiliary_camera_urls"):
        ok_cam, err_cam = _validate_cameras(data.get(cam_field))
        if not ok_cam:
            return False, err_cam
    return True, None
