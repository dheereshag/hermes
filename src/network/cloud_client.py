"""
cloud_client.py
Base URL and stateless IoT device header helpers for Gluvok Cloud API (gluvok.vercel.app).
"""

from __future__ import annotations

from src.config.config_manager import config

GLUVOK_BASE_URL = "https://gluvok.vercel.app"


def get_device_headers() -> dict[str, str]:
    """
    Returns custom authentication headers required for edge device requests.
    - x-device-id: Integer primary key from the devices table
    - x-device-key: Raw pre-shared key
    """
    return {
        "x-device-id": str(config.device_id),
        "x-device-key": config.device_key,
    }
