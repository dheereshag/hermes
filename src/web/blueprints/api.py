from __future__ import annotations

import logging
import time
from typing import Any

import requests
from flask import Blueprint, jsonify, request

from src.config.config_manager import config
from src.core import get_spool_stats
from src.core.telemetry import (
    get_error_counts,
    get_latest_weighment,
    get_system_events,
    record_system_event,
)
from src.web.auth import (
    auth_required,
    create_session_token,
    is_rate_limited,
    record_failed_login,
    verify_credentials,
)
from src.web.validation import validate_config_payload

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _check_argus_online(anpr_url: str) -> bool:
    """Checks if Argus ANPR microservice health endpoint is reachable."""
    health_url = anpr_url.replace("/recognize", "/health")
    try:
        r = requests.get(health_url, timeout=1.5)
        return r.status_code == 200
    except requests.RequestException:
        return False


def _apply_uart_config_changes(
    serial_port: str | None,
    serial_baudrate: int | None,
    old_port: str,
    old_baud: int,
) -> None:
    """Restarts UART reader if serial port or baudrate was modified."""
    port_changed = bool(serial_port and serial_port != old_port)
    baud_changed = bool(serial_baudrate and serial_baudrate != old_baud)
    if not (port_changed or baud_changed):
        return

    try:
        from src.devices.scale import get_uart_reader
        get_uart_reader().restart(config.serial_port, config.serial_baudrate)
        record_system_event(
            "SCALE",
            f"Re-opened UART serial port {config.serial_port} @ {config.serial_baudrate} baud.",
        )
    except (AttributeError, OSError, RuntimeError) as uart_err:
        logger.error(f"[Config] Error restarting UART reader: {uart_err}")


@api_bp.route("/login", methods=["POST"])
def login():
    """Authenticates superadmin credentials and issues a session token."""
    if is_rate_limited():
        return jsonify({
            "success": False,
            "error": "Too many failed login attempts. Please wait 60 seconds.",
        }), 429

    data: dict[str, Any] = request.get_json(silent=True) or {}
    userid = str(data.get("userid", "")).strip()
    password = str(data.get("password", ""))

    if verify_credentials(userid, password):
        token = create_session_token()
        record_system_event("AUTH", f"Superadmin user '{userid}' signed in successfully.")
        return jsonify({
            "success": True,
            "message": "Authentication successful.",
            "token": token,
        }), 200

    record_failed_login()
    record_system_event("AUTH", f"Failed authentication attempt for user '{userid}'.")
    time.sleep(0.5)
    return jsonify({
        "success": False,
        "error": "Invalid user ID or password.",
    }), 401


@api_bp.route("/status", methods=["GET"])
def status():
    """Returns complete real-time operational telemetry snapshot."""
    from src.core.stability import get_current_weight, get_scale_state
    from src.devices.wifi import is_hotspot_active, is_wifi_connected
    from src.integrations.anpr import resolve_anpr_endpoint

    target_argus_url = resolve_anpr_endpoint(config.anpr_server_url)
    argus_online = _check_argus_online(target_argus_url)

    return jsonify({
        "status": "healthy",
        "scale": {
            "port": config.serial_port,
            "baudrate": config.serial_baudrate,
            "state": get_scale_state().name,
            "current_weight": round(get_current_weight(), 3),
        },
        "argus": {
            "url": target_argus_url,
            "online": argus_online,
        },
        "cloud": {
            "center_id": config.center_id,
            "device_id": config.device_id,
            "configured": bool(config.device_id and config.device_key),
        },
        "cameras": {
            "cam1_url": config.anpr_camera_url,
            "auxiliary_urls": config.auxiliary_camera_urls,
        },
        "wifi": {
            "connected": is_wifi_connected(),
            "hotspot_active": is_hotspot_active(),
        },
        "config": {
            "wifi_ssid": config.wifi_ssid,
            "device_id": config.device_id,
            "min_weight": config.weight_threshold,
            "serial_port": config.serial_port,
            "serial_baudrate": config.serial_baudrate,
            "anpr_camera_url": config.anpr_camera_url,
            "auxiliary_camera_urls": config.auxiliary_camera_urls,
            "anpr_server_url": config.anpr_server_url,
        },
        "latest_weighment": get_latest_weighment(),
        "spool": get_spool_stats(),
        "error_counts": get_error_counts(),
        "events": get_system_events(),
    }), 200



@api_bp.route("/config", methods=["GET"])
def get_config():
    """Returns current system configuration values."""
    return jsonify({
        "min_weight": config.weight_threshold,
        "serial_port": config.serial_port,
        "serial_baudrate": config.serial_baudrate,
        "anpr_camera_url": config.anpr_camera_url,
        "auxiliary_camera_urls": config.auxiliary_camera_urls,
        "anpr_server_url": config.anpr_server_url,
        "device_id": config.device_id,
        "device_key": config.device_key,
        "center_id": config.center_id,
    }), 200


@api_bp.route("/config", methods=["POST"])
@auth_required
def post_config():
    """Updates system configuration parameters with strict input sanitization."""
    data: dict[str, Any] = request.get_json(silent=True) or {}
    is_valid, error_msg = validate_config_payload(data)
    if not is_valid:
        return jsonify({"success": False, "error": error_msg or "Invalid config."}), 400

    old_port = config.serial_port
    old_baud = config.serial_baudrate

    config.update_system_config(
        min_weight=data.get("min_weight"),
        serial_port=data.get("serial_port"),
        serial_baudrate=data.get("serial_baudrate"),
        anpr_camera_url=data.get("anpr_camera_url"),
        auxiliary_camera_urls=data.get("auxiliary_camera_urls"),
        anpr_server_url=data.get("anpr_server_url"),
        device_id=data.get("device_id"),
        device_key=data.get("device_key"),
        center_id=data.get("center_id"),
    )


    _apply_uart_config_changes(
        data.get("serial_port"),
        data.get("serial_baudrate"),
        old_port,
        old_baud,
    )

    record_system_event("CONFIG", "System configuration updated via web interface.")
    return jsonify({
        "success": True,
        "message": "System configuration saved and applied dynamically in real-time.",
    }), 200


@api_bp.route("/wifi", methods=["POST"])
@auth_required
def post_wifi():
    """Provisions facility Wi-Fi credentials and attempts immediate network connection."""
    data: dict[str, Any] = request.get_json(silent=True) or {}
    ssid = str(data.get("ssid", "")).strip()
    password = str(data.get("password", ""))

    if not ssid:
        return jsonify({"success": False, "error": "SSID cannot be empty"}), 400

    config.update_wifi_credentials(ssid, password)
    record_system_event("CONFIG", f"Saved Wi-Fi SSID '{ssid}' to config.json. Attempting connection...")

    from src.devices.wifi import connect_to_wifi
    is_connected, msg = connect_to_wifi(ssid, password)

    if is_connected:
        record_system_event("WIFI", f"Successfully connected to '{ssid}'.")
        return jsonify({
            "success": True,
            "message": f"Saved and successfully connected to Wi-Fi '{ssid}'.",
        }), 200

    record_system_event("WIFI", f"Failed connecting to '{ssid}': {msg}")
    return jsonify({
        "success": False,
        "message": f"Saved to config, but connection failed: {msg}",
    }), 400


@api_bp.route("/wifi/clear", methods=["POST"])
@auth_required
def post_wifi_clear():
    """Clears saved Wi-Fi credentials from persistent storage."""
    config.clear_wifi_credentials()
    record_system_event("CONFIG", "Wi-Fi credentials cleared from config.json")
    return jsonify({
        "success": True,
        "message": "Wi-Fi credentials cleared from config.json.",
    }), 200
