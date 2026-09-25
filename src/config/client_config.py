"""client_config.py — Bespoke client deployment configuration."""
from __future__ import annotations

# Cloud credentials (compiled into binary, non-configurable via UI)
DEVICE_ID: str | int = "pi1"
DEVICE_KEY: str = "hardware123"
CENTER_ID: int = 5

# Weighment & OCR thresholds (compiled into binary, non-configurable via UI)
MIN_WEIGHT: float = 70.0
ANPR_SERVER_URL: str = "http://127.0.0.1:8000/recognize"

# Baseline hardware settings (overridable via Web UI, stored in SQLite)
SERIAL_PORT: str = "/dev/ttyUSB0"
SERIAL_BAUDRATE: int = 9600
ANPR_CAMERA_URLS: list[str] = [
    "http://127.0.0.1:8999/front",
    "http://127.0.0.1:8999/rear",
]
AUXILIARY_CAMERA_URLS: list[str] = [
    "http://127.0.0.1:8999/overview",
]

# Baseline Wi-Fi credentials (overridable via Web UI, stored in SQLite)
WIFI_SSID: str = "TestRouter_5G"
WIFI_PASSWORD: str = "SecretPassword123"
