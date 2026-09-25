from __future__ import annotations

import logging
import time
from typing import Any

import requests
from flask import Blueprint, jsonify, request

from src.config import config
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
    """Checks if Argus ANPR microservice is reachable via root or health endpoint."""
    base_url = anpr_url.replace("/recognize", "").rstrip("/") or "http://127.0.0.1:8000"
    try:
        r = requests.get(f"{base_url}/", timeout=1.5)
        if r.status_code == 200:
            return True
        r_health = requests.get(f"{base_url}/health", timeout=1.5)
        return r_health.status_code == 200
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
            "state": get_scale_state().name,
            "current_weight": round(get_current_weight(), 3),
        },
        "argus": {
            "online": argus_online,
        },
        "cloud": {
            "center_id": config.center_id,
            "configured": bool(config.device_id and config.device_key),
        },
        "wifi": {
            "connected": is_wifi_connected(),
            "hotspot_active": is_hotspot_active(),
            "ssid": config.wifi_ssid,
        },
        "config": {
            "wifi_ssid": config.wifi_ssid,
            "center_id": config.center_id,
            "min_weight": config.weight_threshold,
        },
        "latest_weighment": get_latest_weighment(),
        "spool": get_spool_stats(),
        "error_counts": get_error_counts(),
        "events": get_system_events(),
    }), 200


@api_bp.route("/config", methods=["GET"])
@auth_required
def get_config():
    """Returns current system configuration values."""
    return jsonify({
        "min_weight": config.weight_threshold,
        "serial_port": config.serial_port,
        "serial_baudrate": config.serial_baudrate,
        "anpr_camera_url": config.anpr_camera_url,
        "anpr_camera_urls": config.anpr_camera_urls,
        "auxiliary_camera_urls": config.auxiliary_camera_urls,
        "anpr_server_url": config.anpr_server_url,
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
        serial_port=data.get("serial_port"),
        serial_baudrate=data.get("serial_baudrate"),
        anpr_camera_url=data.get("anpr_camera_url"),
        anpr_camera_urls=data.get("anpr_camera_urls"),
        auxiliary_camera_urls=data.get("auxiliary_camera_urls"),
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


@api_bp.route("/wifi/saved", methods=["GET"])
def get_saved_wifi():
    """Returns saved Wi-Fi networks (SSID and metadata, no passwords)."""
    from src.core.wifi_vault import get_saved_wifi_networks
    networks = get_saved_wifi_networks()
    return jsonify({"success": True, "networks": networks}), 200


@api_bp.route("/wifi/saved/<path:ssid>", methods=["DELETE"])
@auth_required
def delete_saved_wifi(ssid: str):
    """Deletes a saved Wi-Fi network from the persistent vault."""
    from src.core.wifi_vault import delete_saved_wifi_network
    deleted = delete_saved_wifi_network(ssid)
    if deleted:
        record_system_event("CONFIG", f"Removed network '{ssid}' from saved Wi-Fi vault.")
        return jsonify({"success": True, "message": f"Network '{ssid}' removed."}), 200
    return jsonify({"success": False, "error": f"Network '{ssid}' not found."}), 404


@api_bp.route("/wifi", methods=["POST"])
@auth_required
def post_wifi():
    """Provisions facility Wi-Fi credentials and attempts immediate network connection."""
    data: dict[str, Any] = request.get_json(silent=True) or {}
    ssid = str(data.get("ssid", "")).strip()
    password = str(data.get("password", ""))

    if not ssid:
        return jsonify({"success": False, "error": "SSID cannot be empty"}), 400

    from src.core.wifi_vault import get_wifi_password, save_wifi_network

    # If no password provided, check if network is already saved in vault
    if not password:
        stored_password = get_wifi_password(ssid)
        if stored_password:
            password = stored_password

    if password:
        save_wifi_network(ssid, password)

    config.update_wifi_credentials(ssid, password)
    record_system_event("CONFIG", f"Saved Wi-Fi SSID '{ssid}' to persistent storage. Attempting connection...")

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
    """Clears saved Wi-Fi credentials from persistent storage and vault."""
    from src.core.wifi_vault import clear_saved_wifi_networks
    config.clear_wifi_credentials()
    clear_saved_wifi_networks()
    record_system_event("CONFIG", "Wi-Fi credentials cleared from persistent storage.")
    return jsonify({
        "success": True,
        "message": "Wi-Fi credentials cleared from persistent storage.",
    }), 200
