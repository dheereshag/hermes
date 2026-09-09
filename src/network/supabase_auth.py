import logging
import time

import requests

from ..config.config_manager import config
from .supabase_client import GLUVOK_BASE_URL, auth_state

logger = logging.getLogger(__name__)


def login_to_supabase() -> bool:
    """
    Authenticates device hardware account against Gluvok API (/api/auth/login).
    Saves access_token, refresh_token, and calculates expiry timestamp.
    """
    username = config.supabase_email.strip()
    password = config.supabase_password

    if not username or not password:
        logger.warning("[Auth] Missing username or password in config.json (sb_email / sb_pass).")
        try:
            from ..web.server import record_error_event, record_system_event
            record_error_event("CLOUD_AUTH_FAILED", "Missing device credentials in config.json.")
            record_system_event("CLOUD", "Auth failed: Missing credentials in config.json")
        except (ImportError, AttributeError):
            pass
        return False

    login_url = f"{GLUVOK_BASE_URL}/api/auth/login"
    logger.info(f"[Auth] Attempting device login to Gluvok API for user '{username}'...")

    headers = {
        "Content-Type": "application/json",
        "Connection": "close"
    }
    payload = {
        "username": username,
        "password": password
    }

    try:
        response = requests.post(login_url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and "access_token" in data:
                auth_state.access_token = data.get("access_token", "")
                auth_state.refresh_token = data.get("refresh_token", "")
                expires_in = int(data.get("expires_in", 900))
                auth_state.expires_at = time.time() + expires_in

                logger.info(f"[Auth] Gluvok Device Login successful! Access token valid for {expires_in}s.")
                try:
                    from ..web.server import record_system_event
                    record_system_event("CLOUD", f"Gluvok API authentication successful for user '{username}'.")
                except (ImportError, AttributeError):
                    pass
                return True

        logger.error(f"[Auth] Login failed with status {response.status_code}: {response.text}")
        try:
            from ..web.server import record_error_event, record_system_event
            record_error_event("CLOUD_AUTH_FAILED", f"Status: {response.status_code}")
            record_system_event("CLOUD", f"Gluvok login failed: HTTP {response.status_code}")
        except (ImportError, AttributeError):
            pass
    except (requests.RequestException, ValueError, KeyError) as e:
        logger.error(f"[Auth] Network exception during Gluvok login: {e}")
        try:
            from ..web.server import record_error_event, record_system_event
            record_error_event("CLOUD_AUTH_FAILED", str(e))
            record_system_event("CLOUD", f"Gluvok login network exception: {e}")
        except (ImportError, AttributeError):
            pass

    return False


def refresh_gluvok_token() -> bool:
    """
    Refreshes expired access_token using refresh_token via /api/auth/refresh.
    """
    if not auth_state.refresh_token:
        logger.warning("[Auth] No refresh token available. Executing full login...")
        return login_to_supabase()

    refresh_url = f"{GLUVOK_BASE_URL}/api/auth/refresh"
    logger.info("[Auth] Attempting access token refresh via Gluvok API...")

    headers = {
        "Content-Type": "application/json",
        "Connection": "close"
    }
    payload = {
        "refresh_token": auth_state.refresh_token
    }

    try:
        response = requests.post(refresh_url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and "access_token" in data:
                auth_state.access_token = data.get("access_token", "")
                if data.get("refresh_token"):
                    auth_state.refresh_token = data.get("refresh_token")
                expires_in = int(data.get("expires_in", 900))
                auth_state.expires_at = time.time() + expires_in

                logger.info(f"[Auth] Gluvok Access Token refreshed successfully! Expires in {expires_in}s.")
                return True

        logger.warning(f"[Auth] Token refresh returned status {response.status_code}. Re-authenticating...")
        auth_state.access_token = ""
        auth_state.refresh_token = ""
        return login_to_supabase()
    except (requests.RequestException, ValueError, KeyError) as e:
        logger.error(f"[Auth] Exception during token refresh: {e}")
        return login_to_supabase()


def ensure_valid_auth() -> bool:
    """Ensures a valid access token is active; refreshes or logs in if needed."""
    if auth_state.is_token_valid:
        return True

    if auth_state.refresh_token:
        return refresh_gluvok_token()

    return login_to_supabase()
