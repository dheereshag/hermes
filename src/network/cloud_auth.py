import logging
import time

import requests

from src.config.config_manager import config
from src.network.cloud_client import GLUVOK_BASE_URL, auth_state

logger = logging.getLogger(__name__)


class WeighbridgeAuthClient:
    """Manage the Gluvok access and refresh token lifecycle."""

    def __init__(self, base_url: str, username: str, password: str, state=auth_state):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.state = state
        self.access_token = state.access_token
        self.refresh_token = state.refresh_token
        self.expires_at = state.expires_at

    def _save_tokens(self, data: dict) -> None:
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        expires_in = int(data.get("expires_in", 900))
        self.expires_at = time.time() + expires_in
        self.state.access_token = self.access_token
        self.state.refresh_token = self.refresh_token
        self.state.expires_at = self.expires_at

    def login(self) -> None:
        response = requests.post(
            f"{self.base_url}/api/auth/login",
            json={"username": self.username, "password": self.password},
            timeout=15,
        )
        response.raise_for_status()
        self._save_tokens(response.json())

    def refresh(self) -> None:
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/refresh",
                json={"refresh_token": self.refresh_token},
                timeout=15,
            )
            response.raise_for_status()
            self._save_tokens(response.json())
        except (requests.RequestException, ValueError, KeyError, TypeError):
            self.login()

    def get_valid_token(self) -> str:
        if not self.access_token or not self.refresh_token:
            self.login()
        elif time.time() >= self.expires_at:
            self.refresh()
        return self.access_token

    def post_entry(self, entry_payload: dict) -> requests.Response:
        token = self.get_valid_token()
        response = requests.post(
            f"{self.base_url}/api/entries",
            json=entry_payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if response.status_code == 401:
            self.refresh()
            response = requests.post(
                f"{self.base_url}/api/entries",
                json=entry_payload,
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=10,
            )
        return response


def _auth_client() -> WeighbridgeAuthClient:
    return WeighbridgeAuthClient(
        GLUVOK_BASE_URL,
        config.api_email.strip(),
        config.api_password,
    )


def _record_auth_failure(message: str) -> None:
    try:
        from src.web.server import record_error_event, record_system_event

        record_error_event("CLOUD_AUTH_FAILED", message)
        record_system_event("CLOUD", f"Auth failed: {message}")
    except (ImportError, AttributeError):
        pass


def login_to_cloud() -> bool:
    """Authenticate the configured device account against the Gluvok API."""
    client = _auth_client()
    if not client.username or not client.password:
        logger.warning(
            "[Auth] Missing username or password in config.json (api_email / api_password)."
        )
        _record_auth_failure("Missing device credentials in config.json.")
        return False

    try:
        logger.info(
            f"[Auth] Attempting device login to Gluvok API for user '{client.username}'..."
        )
        client.login()
        logger.info("[Auth] Gluvok Device Login successful!")
        try:
            from src.web.server import record_system_event

            record_system_event(
                "CLOUD",
                f"Gluvok API authentication successful for user '{client.username}'.",
            )
        except (ImportError, AttributeError):
            pass
        return True
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        logger.error(f"[Auth] Exception during Gluvok login: {error}")
        _record_auth_failure(str(error))
        return False


def refresh_gluvok_token() -> bool:
    """
    Refreshes expired access_token using refresh_token via /api/auth/refresh.
    """
    if not auth_state.refresh_token:
        logger.warning("[Auth] No refresh token available. Executing full login...")
        return login_to_cloud()

    logger.info("[Auth] Attempting access token refresh via Gluvok API...")
    client = _auth_client()
    try:
        client.refresh()
        logger.info("[Auth] Gluvok Access Token refreshed successfully.")
        return True
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        logger.error(f"[Auth] Exception during token refresh: {error}")
        auth_state.access_token = ""
        auth_state.refresh_token = ""
        return login_to_cloud()


def ensure_valid_auth() -> bool:
    """Ensures a valid access token is active; refreshes or logs in if needed."""
    if auth_state.is_token_valid:
        return True

    if auth_state.refresh_token:
        return refresh_gluvok_token()

    return login_to_cloud()
