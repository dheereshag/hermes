from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import requests

from src.config.config_manager import config
from src.network.supabase_client import auth_state
from src.scale.scale_stability import get_current_weight, get_scale_state

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
INDEX_HTML_PATH = os.path.abspath(os.path.join(TEMPLATES_DIR, "index.html"))

# ── Security & Authentication Storage ─────────────────────────────────────────
SUPERADMIN_USER = os.getenv("SUPERADMIN_USER", "superadmin")
SUPERADMIN_PASS = os.getenv("SUPERADMIN_PASS", "Gluvok@241821")

# In-memory active session tokens: token -> expiration timestamp (2 hour sliding lifetime)
_active_sessions: dict[str, float] = {}
_session_lock = threading.Lock()

# Rate limiting for login brute-force defense
_failed_login_attempts: list[float] = []
_login_lock = threading.Lock()

# In-memory recent system events buffer for telemetry feed
_system_events: list[dict[str, str]] = []
_events_lock = threading.Lock()

# Live weighment session status and active error tracking
_latest_weighment: dict[str, Any] = {
    "session_id": None,
    "plate": None,
    "weight": 0.0,
    "timestamp": None,
    "is_error": False,
    "status_code": "READY",
}
_error_counts: dict[str, int] = {}
_live_lock = threading.Lock()


def record_system_event(source: str, message: str):
    """Appends an event to the circular telemetry log (max 20 entries)."""
    with _events_lock:
        if len(_system_events) >= 20:
            _system_events.pop(0)
        _system_events.append({
            "time": time.strftime("%H:%M:%S"),
            "source": source,
            "message": message,
        })


def record_weighment_result(session_id: str, plate: str, weight: float, is_error: bool = False, status_code: str = "SUCCESS"):
    """Records the latest weighbridge session outcome and updates live error counters."""
    with _live_lock:
        _latest_weighment["session_id"] = session_id
        _latest_weighment["plate"] = plate
        _latest_weighment["weight"] = weight
        _latest_weighment["timestamp"] = time.strftime("%H:%M:%S")
        _latest_weighment["is_error"] = is_error
        _latest_weighment["status_code"] = status_code

        if is_error or status_code not in ("SUCCESS", "READY"):
            _error_counts[status_code] = _error_counts.get(status_code, 0) + 1


def record_error_event(error_code: str, message: str = ""):
    """Explicitly increments live occurrence count for a system error code."""
    with _live_lock:
        _error_counts[error_code] = _error_counts.get(error_code, 0) + 1


def get_latest_weighment() -> dict[str, Any]:
    with _live_lock:
        return dict(_latest_weighment)


def get_error_counts() -> dict[str, int]:
    with _live_lock:
        return dict(_error_counts)


# ── Auth Helpers ─────────────────────────────────────────────────────────────
def create_session_token() -> str:
    token = secrets.token_hex(32)
    with _session_lock:
        # Session valid for 2 hours (7200 seconds)
        _active_sessions[token] = time.time() + 7200.0
    return token


def validate_session_token(token: str | None) -> bool:
    if not token:
        return False
    now = time.time()
    with _session_lock:
        exp = _active_sessions.get(token)
        if exp and exp > now:
            # Slide session window on activity
            _active_sessions[token] = now + 7200.0
            return True
        elif exp:
            del _active_sessions[token]
    return False


def is_rate_limited() -> bool:
    """Brute force mitigation: max 5 failed logins within 60 seconds."""
    now = time.time()
    with _login_lock:
        # Keep only attempts in last 60 seconds
        _failed_login_attempts[:] = [t for t in _failed_login_attempts if now - t < 60.0]
        return len(_failed_login_attempts) >= 5


def record_failed_login():
    with _login_lock:
        _failed_login_attempts.append(time.time())


class FallbackHTTPRequestHandler(BaseHTTPRequestHandler):
    """Request handler serving the fallback Tailwind CSS console and REST APIs."""

    def log_message(self, format: str, *args: Any):
        # Silence default standard HTTP access logs to keep terminal clean
        pass

    def _send_json_response(self, data: dict[str, Any], status_code: int = 200):
        response_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(response_bytes)

    def _check_auth(self) -> bool:
        """Extracts Bearer token or X-Auth-Token header and validates."""
        auth_hdr = self.headers.get("Authorization", "")
        token = ""
        if auth_hdr.startswith("Bearer "):
            token = auth_hdr[7:].strip()
        if not token:
            token = self.headers.get("X-Auth-Token", "").strip()
        return validate_session_token(token)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Auth-Token")
        self.end_headers()

    def do_GET(self):
        # Path traversal guard: strictly map allowed routes
        path = self.path.split("?")[0]
        valid_page_routes = (
            "/",
            "/index",
            "/scale",
            "/anpr",
            "/cloud",
            "/wifi",
            "/telemetry",
            "/errors",
            "/config",
        )
        if path in valid_page_routes or path.startswith("/index"):
            self._serve_index_html()
        elif path == "/api/status":
            self._handle_get_status()
        elif path == "/api/config":
            self._handle_get_config()
        else:
            self._send_json_response({"error": "Resource not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/login":
            self._handle_post_login()
        elif path == "/api/wifi":
            if not self._check_auth():
                self._send_json_response({"success": False, "error": "Unauthorized. Please sign in."}, 401)
                return
            self._handle_post_wifi()
        elif path == "/api/wifi/clear":
            if not self._check_auth():
                self._send_json_response({"success": False, "error": "Unauthorized. Please sign in."}, 401)
                return
            self._handle_post_wifi_clear()
        elif path == "/api/config":
            if not self._check_auth():
                self._send_json_response({"success": False, "error": "Unauthorized. Superadmin credentials required."}, 401)
                return
            self._handle_post_config()
        else:
            self._send_json_response({"error": "Endpoint not found"}, 404)

    def _serve_index_html(self):
        if not os.path.exists(INDEX_HTML_PATH):
            self.send_error(500, "Dashboard index.html template missing")
            return

        try:
            with open(INDEX_HTML_PATH, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)
        except OSError as e:
            self.send_error(500, f"Error reading index.html: {e}")

    def _handle_post_login(self):
        """Authenticates superadmin credentials and issues cryptographically secure session token."""
        if is_rate_limited():
            self._send_json_response({
                "success": False,
                "error": "Too many failed login attempts. Please wait 60 seconds.",
            }, 429)
            return

        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len)

        try:
            data = json.loads(post_body.decode("utf-8"))
            userid = str(data.get("userid", "")).strip()
            password = str(data.get("password", ""))

            # Constant-time comparison to prevent timing attacks
            user_ok = secrets.compare_digest(userid, SUPERADMIN_USER)
            pass_ok = secrets.compare_digest(password, SUPERADMIN_PASS)

            if user_ok and pass_ok:
                token = create_session_token()
                record_system_event("AUTH", f"Superadmin user '{userid}' signed in successfully.")
                self._send_json_response({
                    "success": True,
                    "message": "Authentication successful.",
                    "token": token,
                })
            else:
                record_failed_login()
                record_system_event("AUTH", f"Failed authentication attempt for user '{userid}'.")
                # Intentionally delay response slightly to mitigate rapid automated attempts
                time.sleep(0.5)
                self._send_json_response({
                    "success": False,
                    "error": "Invalid user ID or password.",
                }, 401)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._send_json_response({"success": False, "error": f"Invalid payload: {e}"}, 400)

    def _handle_get_status(self):
        from src.camera.anpr_client import resolve_anpr_endpoint
        target_argus_url = resolve_anpr_endpoint(config.anpr_server_url)
        argus_health_url = target_argus_url.replace("/recognize", "/health")
        argus_online = False
        try:
            r = requests.get(argus_health_url, timeout=1.5)
            argus_online = r.status_code == 200
        except requests.RequestException:
            argus_online = False

        with _events_lock:
            events_copy = list(_system_events)

        from src.network.wifi_manager import is_hotspot_active, is_wifi_connected

        status_data = {
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
            "supabase": {
                "center_id": config.supabase_center_id,
                "authenticated": auth_state.is_token_valid,
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
                "operator_email": config.supabase_email,
                "min_weight": config.supabase_weight_threshold,
                "serial_port": config.serial_port,
                "serial_baudrate": config.serial_baudrate,
                "anpr_camera_url": config.anpr_camera_url,
                "auxiliary_camera_urls": config.auxiliary_camera_urls,
                "anpr_server_url": config.anpr_server_url,
            },
            "latest_weighment": get_latest_weighment(),
            "error_counts": get_error_counts(),
            "events": events_copy,
        }
        self._send_json_response(status_data)

    def _handle_post_wifi(self):
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len)

        try:
            data = json.loads(post_body.decode("utf-8"))
            ssid = data.get("ssid", "").strip()
            password = data.get("password", "")

            if not ssid:
                self._send_json_response({"success": False, "error": "SSID cannot be empty"}, 400)
                return

            config.update_wifi_credentials(ssid, password)
            record_system_event("CONFIG", f"Saved Wi-Fi SSID '{ssid}' to config.json. Attempting connection...")

            from src.network.wifi_manager import connect_to_wifi
            connected, msg = connect_to_wifi(ssid, password)

            if connected:
                record_system_event("WIFI", f"Successfully connected to '{ssid}'.")
                self._send_json_response({
                    "success": True,
                    "message": f"Saved and successfully connected to Wi-Fi '{ssid}'.",
                })
            else:
                record_system_event("WIFI", f"Failed connecting to '{ssid}': {msg}")
                self._send_json_response({
                    "success": False,
                    "message": f"Saved to config, but connection failed: {msg}",
                }, 400)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._send_json_response({"success": False, "error": f"Invalid JSON payload: {e}"}, 400)

    def _handle_post_wifi_clear(self):
        config.clear_wifi_credentials()
        record_system_event("CONFIG", "Wi-Fi credentials cleared from config.json")
        self._send_json_response({
            "success": True,
            "message": "Wi-Fi credentials cleared from config.json.",
        })

    def _handle_get_config(self):
        """Returns current system configuration values."""
        config_data = {
            "min_weight": config.supabase_weight_threshold,
            "serial_port": config.serial_port,
            "serial_baudrate": config.serial_baudrate,
            "anpr_camera_url": config.anpr_camera_url,
            "auxiliary_camera_urls": config.auxiliary_camera_urls,
            "anpr_server_url": config.anpr_server_url,
        }
        self._send_json_response(config_data)

    def _handle_post_config(self):
        """Updates system configuration from JSON payload with strict input sanitization."""
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len)

        try:
            data = json.loads(post_body.decode("utf-8"))

            min_weight = data.get("min_weight")
            serial_port = data.get("serial_port")
            serial_baudrate = data.get("serial_baudrate")
            anpr_camera_url = data.get("anpr_camera_url")
            auxiliary_camera_urls = data.get("auxiliary_camera_urls")
            anpr_server_url = data.get("anpr_server_url")

            # ── Strict Input Validation & Sanitization ─────────────────────
            if min_weight is not None:
                try:
                    min_weight = float(min_weight)
                    if min_weight < 0 or min_weight > 100000.0:
                        self._send_json_response({"success": False, "error": "Threshold weight must be between 0 and 100,000 kg."}, 400)
                        return
                except (ValueError, TypeError):
                    self._send_json_response({"success": False, "error": "Invalid threshold weight value."}, 400)
                    return

            if serial_baudrate is not None:
                try:
                    serial_baudrate = int(serial_baudrate)
                    if serial_baudrate not in (300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200):
                        self._send_json_response({"success": False, "error": "Invalid baud rate value."}, 400)
                        return
                except (ValueError, TypeError):
                    self._send_json_response({"success": False, "error": "Invalid baud rate value."}, 400)
                    return

            if serial_port is not None:
                sp_str = str(serial_port).strip()
                # Ensure device path only contains allowed path characters (e.g. /dev/ttyAMA0, /dev/ttyS0, COM1)
                if sp_str and not re.match(r"^[a-zA-Z0-9_\-/\.]{1,64}$", sp_str):
                    self._send_json_response({"success": False, "error": "Invalid serial port path character set."}, 400)
                    return

            def is_valid_url(u: str) -> bool:
                if not u:
                    return True
                u_lower = u.lower()
                return u_lower.startswith(("http://", "https://", "rtsp://")) and not any(c in u for c in ("\r", "\n", "\0", " "))

            if anpr_camera_url is not None and not is_valid_url(str(anpr_camera_url)):
                self._send_json_response({"success": False, "error": "ANPR Camera URL must start with http://, https://, or rtsp://"}, 400)
                return

            if anpr_server_url is not None and not is_valid_url(str(anpr_server_url)):
                self._send_json_response({"success": False, "error": "ANPR Server URL must start with http:// or https://"}, 400)
                return

            if auxiliary_camera_urls is not None:
                if not isinstance(auxiliary_camera_urls, list):
                    self._send_json_response({"success": False, "error": "Auxiliary camera URLs must be a list."}, 400)
                    return
                for u in auxiliary_camera_urls:
                    if not is_valid_url(str(u)):
                        self._send_json_response({"success": False, "error": f"Invalid auxiliary camera URL: {u}"}, 400)
                        return

            old_port = config.serial_port
            old_baud = config.serial_baudrate

            config.update_system_config(
                min_weight=min_weight,
                serial_port=serial_port,
                serial_baudrate=serial_baudrate,
                anpr_camera_url=anpr_camera_url,
                auxiliary_camera_urls=auxiliary_camera_urls,
                anpr_server_url=anpr_server_url,
            )

            # Trigger live UART reader re-initialization if serial port or baud rate changed
            if (serial_port and serial_port != old_port) or (serial_baudrate and serial_baudrate != old_baud):
                try:
                    from src.scale.scale_uart import get_uart_reader
                    get_uart_reader().restart(config.serial_port, config.serial_baudrate)
                    record_system_event("SCALE", f"Re-opened UART serial port {config.serial_port} @ {config.serial_baudrate} baud.")
                except (AttributeError, OSError, RuntimeError) as uart_err:
                    logger.error(f"[Config] Error restarting UART reader: {uart_err}")

            record_system_event("CONFIG", "System configuration updated via web interface.")

            self._send_json_response({
                "success": True,
                "message": "System configuration saved and applied dynamically in real-time.",
            })
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._send_json_response({"success": False, "error": f"Invalid JSON payload: {e}"}, 400)


class FallbackWebServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._is_running = False

    def start(self):
        if self._is_running:
            return

        try:
            self._server = ThreadingHTTPServer((self.host, self.port), FallbackHTTPRequestHandler)
            self._is_running = True
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="FallbackWebServer",
                daemon=True,
            )
            self._thread.start()
            logger.info(f"[WebServer] Fallback diagnostics web server running at http://{self.host}:{self.port}")
            record_system_event("SYSTEM", f"Fallback web server started on port {self.port}")
        except OSError as e:
            logger.error(f"[WebServer] Failed to bind fallback web server on port {self.port}: {e}")

    def stop(self):
        if not self._is_running or not self._server:
            return

        self._is_running = False
        try:
            self._server.shutdown()
            self._server.server_close()
            logger.info("[WebServer] Fallback web server stopped.")
        except OSError as e:
            logger.debug(f"[WebServer] Error stopping web server: {e}")


# Module-level singleton
web_server = FallbackWebServer()


def start_web_server(host: str = "0.0.0.0", port: int = 8080):
    web_server.host = host
    web_server.port = port
    web_server.start()


def stop_web_server():
    web_server.stop()
