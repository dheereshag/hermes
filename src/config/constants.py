"""
constants.py — Centralized System & Hardware Constants
=====================================================
Defines system-wide operational constants, timeouts, buffer limits, and regex patterns.
"""

from __future__ import annotations

import re

# ── Scale Indicator Serial Constants ──────────────────────────────────────────
INTER_CHAR_TIMEOUT_S = 0.3      # Inter-character silence flush timeout (300ms)
MAX_BUFFER_LEN = 256            # Maximum raw serial line buffer length
SCALE_TIMEOUT = 0.05            # Serial read non-blocking timeout (50ms)
DEFAULT_SERIAL_PORT = "/dev/ttyAMA0"
DEFAULT_SERIAL_BAUDRATE = 1200

# ── Scale Stability Constants ─────────────────────────────────────────────────
STABILITY_TOLERANCE = 2.0       # ±2.0 kg allowed variation
STABILITY_DURATION = 10.0       # 10.0 seconds continuous stability required
DEFAULT_WEIGHT_THRESHOLD = 50.0 # Minimum weight threshold in kg to start a session

# ── Camera & ANPR Timing ──────────────────────────────────────────────────────
ANPR_CAPTURE_INTERVAL = 2.0     # Seconds between Camera ANPR capture attempts
POST_STABILITY_DURATION = 10.0   # Seconds to capture ANPR after stability confirmed
CAMERA_TIMEOUT = 3.0            # Seconds allowed for individual camera HTTP snapshot
ANPR_SERVER_TIMEOUT = 15.0      # Seconds allowed for Argus ANPR HTTP POST
MAX_PARALLEL_CAMERA_WORKERS = 4 # Thread pool workers for concurrent auxiliary camera captures
DEFAULT_ANPR_CAMERA_URLS = [
    "http://192.168.1.101/cgi-bin/snapshot.cgi",
]
DEFAULT_AUXILIARY_CAMERA_URLS = [
    "http://192.168.1.102/cgi-bin/snapshot.cgi",
    "http://192.168.1.103/cgi-bin/snapshot.cgi",
    "http://192.168.1.104/cgi-bin/snapshot.cgi",
]

# ── Emergency Wi-Fi Hotspot Constants ─────────────────────────────────────────
HOTSPOT_CON_NAME = "Gluvok-Hotspot"
DEFAULT_HOTSPOT_SSID = "Gluvok-Setup"
DEFAULT_HOTSPOT_PASS = "gluvok1234"
DEFAULT_WIFI_WATCHDOG_INTERVAL = 30.0

# ── Gluvok Cloud API Constants ────────────────────────────────────────────────
GLUVOK_BASE_URL = "https://gluvok.vercel.app"
CLOUD_POST_TIMEOUT = 20.0       # Network timeout in seconds for Gluvok API entry POST
DEFAULT_DEVICE_ID = "pi1"
DEFAULT_DEVICE_KEY = "hardware123"
DEFAULT_CENTER_ID = 1


# Indian vehicle registration regex pattern (e.g. MH12AB1234, DL1CAB1234, 22BH1234AA)
INDIAN_PLATE_REGEX = re.compile(
    r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$|^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$"
)

# ── SQLite Outbox Spool Constants ─────────────────────────────────────────────
DEFAULT_DB_PATH = "data/hermes.db"
SPOOL_LEASE_DURATION_S = 60.0    # Atomic upload lease duration (60s)
SPOOL_WORKER_POLL_INTERVAL = 5.0 # Seconds between outbox sweeps
SPOOL_BASE_RETRY_DELAY = 5.0     # Initial retry backoff in seconds
SPOOL_MAX_RETRY_DELAY = 300.0    # Maximum retry backoff in seconds (5 min)

