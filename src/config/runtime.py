"""runtime.py — Runtime configuration overrides mutator."""
from __future__ import annotations

import threading
from typing import Any

from src.config.store import load_overrides, set_override


class RuntimeConfig:
    def __init__(self, db_path: str | None = None) -> None:
        self._lock = threading.RLock()
        self.db_path = db_path
        self._overrides: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        with self._lock:
            self._overrides = load_overrides(self.db_path)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._overrides.get(key, default)

    def update_system(self, **kwargs: Any) -> None:
        with self._lock:
            for k in ("serial_port", "serial_baudrate", "auxiliary_camera_urls"):
                if kwargs.get(k) is not None:
                    set_override(k, kwargs[k], self.db_path)
            if kwargs.get("anpr_camera_urls") is not None:
                cleaned = [str(u).strip() for u in kwargs["anpr_camera_urls"] if str(u).strip()]
                if cleaned:
                    set_override("anpr_camera_urls", cleaned, self.db_path)
            elif kwargs.get("anpr_camera_url") is not None:
                val = str(kwargs["anpr_camera_url"]).strip()
                if val:
                    set_override("anpr_camera_urls", [val], self.db_path)
            self.reload()

    def update_wifi(self, ssid: str, password: str) -> None:
        with self._lock:
            set_override("wifi_ssid", ssid, self.db_path)
            set_override("wifi_password", password, self.db_path)
            self.reload()

    def clear_wifi(self) -> None:
        with self._lock:
            set_override("wifi_ssid", "", self.db_path)
            set_override("wifi_password", "", self.db_path)
            self.reload()
