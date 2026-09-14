"""
main.py — Gluvok Weighment & ANPR Integration
==============================================
Core weighment indicator and ANPR multi-camera capture application.

Module map:
  src/config/    — JSON-backed settings manager & camera configurations
  src/network/   — Cloud login, profile resolver, payload POST
  src/scale/     — PySerial UART stream reader, 10s stability state machine
  src/camera/    — Multi-camera snapshots, ANPR client, session lifecycle
"""

import logging
import signal
import sys
import time

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ── Import core modules ───────────────────────────────────────────────────────
from src.camera.session_manager import session_manager
from src.config.config_manager import config
from src.network.wifi_manager import start_wifi_watchdog, stop_wifi_watchdog
from src.scale.scale_stability import scale_state_machine
from src.scale.scale_uart import get_uart_reader
from src.web.server import start_web_server, stop_web_server


# ── Graceful shutdown ─────────────────────────────────────────────────────────
def shutdown(signum, frame):
    logger.info("\n[Main] Shutdown signal received. Cleaning up...")
    get_uart_reader().stop()
    stop_web_server()
    stop_wifi_watchdog()
    sys.exit(0)


signal.signal(signal.SIGINT,  shutdown)
signal.signal(signal.SIGTERM, shutdown)

# ─────────────────────────────────────────────────────────────────────────────
#  SETUP
# ─────────────────────────────────────────────────────────────────────────────
def setup():
    logger.info("")
    logger.info("==============================================")
    logger.info("Gluvok Weighment & ANPR System Starting...")
    logger.info("==============================================")

    # Start UART scale reader thread
    get_uart_reader().start()

    # Start fallback diagnostics and Wi-Fi configuration web server
    start_web_server(port=8080)

    # Start automatic Wi-Fi watchdog & emergency hotspot monitor
    start_wifi_watchdog(interval=30.0)


    # Log active settings from config.json
    logger.info(
        f"[Config] Device ID: {config.device_id} | "
        f"Center ID: {config.center_id} | "
        f"Threshold: {config.weight_threshold:.1f} kg"
    )

    # Verify Gluvok Cloud device credentials
    if config.device_id and config.device_key:
        logger.info(f"[Auth] Gluvok device authentication configured for Device ID: {config.device_id}")
    else:
        logger.warning("[Auth] Gluvok device credentials (device_id, device_key) not configured in config.json.")


def loop():
    completed_package = session_manager.check_session_progress()
    if completed_package:
        scale_state_machine._trigger_upload(completed_package)
    time.sleep(1)

# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    setup()
    while True:
        try:
            loop()
        except KeyboardInterrupt:
            break
