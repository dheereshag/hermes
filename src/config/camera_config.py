"""
camera_config.py
Configuration for IP Cameras, ANPR Server, and Session Timers.
Uses dynamic property/getter evaluation so changes made via the System Config web page
take effect immediately on the next capture cycle without requiring a process restart.
"""

from src.config.config_manager import config


def get_anpr_camera_url() -> str:
    """Returns current ANPR camera URL from persistent config."""
    return config.anpr_camera_url

def get_auxiliary_camera_urls() -> list[str]:
    """Returns current auxiliary camera URLs list from persistent config."""
    return config.auxiliary_camera_urls

def get_anpr_server_url() -> str:
    """Returns current ANPR server URL override or default local endpoint."""
    return config.anpr_server_url or "http://127.0.0.1:8000/recognize"

# Dynamic module-level attribute lookup fallback for backward compatibility
def __getattr__(name: str):
    if name == "ANPR_CAMERA_URL":
        return get_anpr_camera_url()
    elif name == "AUXILIARY_CAMERA_URLS":
        return get_auxiliary_camera_urls()
    elif name == "ANPR_SERVER_URL":
        return get_anpr_server_url()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

# ── Timing & Timeouts ────────────────────────────────────────────────────────
ANPR_CAPTURE_INTERVAL = 2.0        # Seconds between Camera 1 ANPR captures
POST_STABILITY_DURATION = 10.0      # Additional seconds to capture ANPR after stability
CAMERA_TIMEOUT = 3.0               # Seconds allowed for individual camera snapshot HTTP request
ANPR_SERVER_TIMEOUT = 15.0         # Seconds allowed for ANPR HTTP POST request (YOLO+OCR on RPi takes 6-10s)
MAX_PARALLEL_CAMERA_WORKERS = 4    # Maximum concurrent thread pool workers for snapshots
