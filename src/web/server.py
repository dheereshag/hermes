from __future__ import annotations

import logging
import threading

from werkzeug.serving import BaseWSGIServer, make_server

from src.core.telemetry import (
    get_error_counts,
    get_latest_weighment,
    get_system_events,
    record_error_event,
    record_system_event,
    record_weighment_result,
    reset_state,
)
from src.web.app import create_app

logger = logging.getLogger(__name__)


class FallbackWebServer:
    """Threaded web server runner serving the Flask diagnostics console."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self._server: BaseWSGIServer | None = None
        self._thread: threading.Thread | None = None
        self._is_running = False

    def start(self) -> None:
        """Starts the Werkzeug WSGI server in a background daemon thread."""
        if self._is_running:
            return

        try:
            flask_app = create_app()
            # Silence standard Werkzeug request logging to keep terminal clean
            logging.getLogger("werkzeug").setLevel(logging.WARNING)

            self._server = make_server(self.host, self.port, flask_app)
            self._is_running = True
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="FallbackWebServer",
                daemon=True,
            )
            self._thread.start()
            logger.info(f"[WebServer] Diagnostics web server running at http://{self.host}:{self.port}")
            record_system_event("SYSTEM", f"Diagnostics web server started on port {self.port}")
        except OSError as e:
            logger.error(f"[WebServer] Failed to bind web server on port {self.port}: {e}")

    def stop(self) -> None:
        """Gracefully shuts down the running WSGI server."""
        if not self._is_running or not self._server:
            return

        self._is_running = False
        try:
            self._server.shutdown()
            self._server.server_close()
            logger.info("[WebServer] Diagnostics web server stopped.")
        except OSError as e:
            logger.debug(f"[WebServer] Error stopping web server: {e}")
        finally:
            self._server = None


# Module-level singleton
web_server = FallbackWebServer()


def start_web_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    web_server.host = host
    web_server.port = port
    web_server.start()


def stop_web_server() -> None:
    web_server.stop()


__all__ = [
    "FallbackWebServer",
    "get_error_counts",
    "get_latest_weighment",
    "get_system_events",
    "record_error_event",
    "record_system_event",
    "record_weighment_result",
    "reset_state",
    "start_web_server",
    "stop_web_server",
    "web_server",
]
