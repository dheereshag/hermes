"""
main.py — Gluvok Weighment & ANPR Integration
==============================================
Core weighment indicator and ANPR multi-camera capture application.

Layer architecture:
  src/core/         — Session lifecycle coordinator & 10s stability state machine
  src/devices/      — Hardware drivers (Scale serial stream, Cameras, Wi-Fi watchdog)
  src/integrations/ — External services (Argus ANPR microservice, Gluvok Cloud API)
  src/web/          — Diagnostics web console (:8080) & local REST APIs
  src/config/       — Centralized settings & operational constants
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

# ── Import decoupled layer modules ───────────────────────────────────────────
from src.config import config
from src.core import (
    init_db,
    recover_stranded_leases,
    scale_state_machine,
    session_manager,
    spool_worker,
)
from src.devices import (
    get_uart_reader,
    led_controller,
    start_wifi_watchdog,
    stop_wifi_watchdog,
)
from src.web import start_web_server, stop_web_server


# ── Graceful shutdown ─────────────────────────────────────────────────────────
def shutdown(signum, frame):
    logger.info("\n[Main] Shutdown signal received. Cleaning up...")
    led_controller.cleanup()
    spool_worker.stop()
    get_uart_reader().stop()
    stop_web_server()
    stop_wifi_watchdog()
    session_manager.reset_session()
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

    # Initialize RGB LED indicator: Green (1s) -> Red (1s) -> Blue (1s) -> Idle Green
    led_controller.startup_test(delay=1.0)

    # Start UART scale reader thread
    get_uart_reader().start()

    # Start fallback diagnostics and Wi-Fi configuration web server
    start_web_server(port=8080)

    # Start automatic Wi-Fi watchdog & emergency hotspot monitor
    start_wifi_watchdog(interval=30.0)

    # Initialize SQLite durable outbox spool and start dispatcher
    init_db()
    recover_stranded_leases()
    spool_worker.start()


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
