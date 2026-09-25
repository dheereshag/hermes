"""
wifi.py — Raspberry Pi Wi-Fi & Emergency Hotspot Driver
======================================================
Manages Raspberry Pi Wi-Fi connectivity and automatic emergency Access Point (Hotspot) fallback.
Uses NetworkManager (nmcli) to detect connection drops and spin up the 'hermes' hotspot.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading

from src.config.constants import (
    DEFAULT_HOTSPOT_PASS,
    DEFAULT_HOTSPOT_SSID,
    DEFAULT_WIFI_WATCHDOG_INTERVAL,
    HOTSPOT_CON_NAME,
)

logger = logging.getLogger(__name__)

_hotspot_active = False
_watchdog_thread: threading.Thread | None = None
_watchdog_stop_event = threading.Event()
_wifi_lock = threading.Lock()


def is_nmcli_available() -> bool:
    """Checks if nmcli (NetworkManager) is installed on the system."""
    return shutil.which("nmcli") is not None


def _run_nmcli(
    args: list[str],
    timeout: float = 10,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Runs nmcli command, automatically attempting sudo elevation if unprivileged."""
    cmd = ["nmcli", *args]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    is_root = getattr(os, "geteuid", lambda: 0)() == 0
    if res.returncode != 0 and not is_root and shutil.which("sudo"):
        sudo_cmd = ["sudo", "-n", "nmcli", *args]
        sudo_res = subprocess.run(
            sudo_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if sudo_res.returncode == 0:
            return sudo_res
        if check:
            raise subprocess.CalledProcessError(
                sudo_res.returncode,
                sudo_cmd,
                sudo_res.stdout,
                sudo_res.stderr,
            )
        return sudo_res

    if check and res.returncode != 0:
        raise subprocess.CalledProcessError(res.returncode, cmd, res.stdout, res.stderr)
    return res


def get_wifi_interface() -> str:
    """Detects active Wi-Fi interface name via nmcli or falls back to 'wlan0'."""
    if not is_nmcli_available():
        return "wlan0"
    try:
        res = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE", "dev"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            for line in res.stdout.strip().splitlines():
                parts = line.split(":")
                if len(parts) >= 2 and parts[1].strip() == "wifi" and (dev := parts[0].strip()):
                    return dev
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug(f"[WiFi] Error detecting Wi-Fi interface: {e}")
    return "wlan0"


def is_wifi_connected() -> bool:
    """
    Checks if active Wi-Fi is connected to an external network (not in AP/hotspot mode).
    Returns True if connected to an external Wi-Fi SSID, False otherwise.
    """
    if not is_nmcli_available():
        # Fallback check for non-Linux or mock environments
        return False

    try:
        # Query active NetworkManager Wi-Fi connections
        res = subprocess.run(
            ["nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "dev"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode != 0:
            return False

        for line in res.stdout.strip().splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[0] == "wifi" and parts[1] == "connected":
                con_name = parts[2]
                # If connected but it's our own hotspot, it's not a normal external Wi-Fi
                if con_name != HOTSPOT_CON_NAME:
                    return True
        return False
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug(f"[WiFi] Error checking Wi-Fi status: {e}")
        return False


def is_hotspot_active() -> bool:
    """Checks if emergency hotspot is actively broadcasting in NetworkManager."""
    global _hotspot_active
    if not is_nmcli_available():
        return _hotspot_active
    try:
        res = _run_nmcli(["-t", "-f", "TYPE,STATE,CONNECTION", "dev"], timeout=5, check=False)
        if res.returncode == 0:
            for line in res.stdout.strip().splitlines():
                parts = line.split(":")
                if (
                    len(parts) >= 3
                    and parts[0] == "wifi"
                    and parts[1] == "connected"
                    and parts[2] == HOTSPOT_CON_NAME
                ):
                    _hotspot_active = True
                    return True
        _hotspot_active = False
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug(f"[WiFi] Error checking hotspot status: {e}")
    return False


def _activate_hotspot_connection(ssid: str, password: str, ifname: str | None = None) -> None:
    """Create, configure, and bring up the emergency AP via nmcli."""
    dev = ifname or get_wifi_interface()
    _run_nmcli(["connection", "delete", HOTSPOT_CON_NAME], timeout=5, check=False)
    _run_nmcli(
        [
            "connection", "add",
            "type", "wifi",
            "ifname", dev,
            "con-name", HOTSPOT_CON_NAME,
            "autoconnect", "no",
            "ssid", ssid,
        ],
        timeout=5,
        check=True,
    )
    _run_nmcli(
        [
            "connection", "modify", HOTSPOT_CON_NAME,
            "802-11-wireless.mode", "ap",
            "802-11-wireless.band", "bg",
            "ipv4.method", "shared",
            "wifi-sec.key-mgmt", "wpa-psk",
            "wifi-sec.psk", password,
        ],
        timeout=5,
        check=True,
    )
    _run_nmcli(["connection", "up", HOTSPOT_CON_NAME], timeout=10, check=True)


def start_emergency_hotspot(
    ssid: str = DEFAULT_HOTSPOT_SSID,
    password: str = DEFAULT_HOTSPOT_PASS,
) -> bool:
    """
    Starts the emergency Wi-Fi Access Point (Hotspot) using nmcli.
    Broadcasts 'hermes' with default IP 10.42.0.1.
    """
    global _hotspot_active
    with _wifi_lock:
        if is_hotspot_active():
            _hotspot_active = True
            return True

        if not is_nmcli_available():
            logger.info("[WiFi] nmcli not available. Simulating hotspot start in current environment.")
            _hotspot_active = True
            return True

        try:
            _activate_hotspot_connection(ssid, password)
            _hotspot_active = True
            logger.info(
                f"[WiFi] Emergency Access Point active! SSID: '{ssid}' | "
                f"Password: '{password}' | Web Console: http://10.42.0.1:8080"
            )
            return True
        except (subprocess.SubprocessError, OSError) as e:
            detail = ""
            if isinstance(e, subprocess.CalledProcessError) and e.stderr:
                detail = f" | Detail: {e.stderr.strip()}"
            logger.error(f"[WiFi] Failed to start emergency hotspot: {e}{detail}")
            _hotspot_active = False
            return False


def stop_emergency_hotspot() -> bool:
    """Tears down the emergency Access Point on wlan0."""
    global _hotspot_active
    with _wifi_lock:
        if not is_hotspot_active():
            _hotspot_active = False
            return True

        if not is_nmcli_available():
            _hotspot_active = False
            return True

        try:
            _run_nmcli(["connection", "down", HOTSPOT_CON_NAME], timeout=5, check=False)
            _hotspot_active = False
            logger.info("[WiFi] Emergency Access Point stopped.")
            return True
        except (subprocess.SubprocessError, OSError) as e:
            detail = ""
            if isinstance(e, subprocess.CalledProcessError) and e.stderr:
                detail = f" | Detail: {e.stderr.strip()}"
            logger.error(f"[WiFi] Error stopping emergency hotspot: {e}{detail}")
            return False


def get_existing_profile(ssid: str) -> str | None:
    """Returns profile name if an existing Wi-Fi connection profile matches the SSID."""
    if not is_nmcli_available():
        return None
    try:
        res = _run_nmcli(["-t", "-f", "NAME,TYPE", "connection", "show"], timeout=5, check=False)
        if res.returncode == 0:
            for line in res.stdout.strip().splitlines():
                parts = line.split(":")
                if len(parts) >= 2 and parts[1].strip() in ("802-11-wireless", "wifi") and parts[0].strip() == ssid:
                    return parts[0].strip()
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug(f"[WiFi] Error checking existing profiles for '{ssid}': {e}")
    return None


def connect_to_wifi(ssid: str, password: str) -> tuple[bool, str]:
    """
    Attempts to connect to the specified Wi-Fi network using nmcli.
    If connected successfully, tears down the emergency hotspot.
    """
    if not ssid:
        return False, "SSID cannot be empty."

    if not is_nmcli_available():
        logger.info(f"[WiFi] nmcli not available. Mock connected to '{ssid}'.")
        stop_emergency_hotspot()
        return True, f"Connected to '{ssid}' (simulated)."

    logger.info(f"[WiFi] Attempting connection to Wi-Fi SSID: '{ssid}'...")
    try:
        # Stop hotspot temporarily to free up the wireless device
        if is_hotspot_active():
            _run_nmcli(["connection", "down", HOTSPOT_CON_NAME], timeout=5, check=False)

        existing_profile = get_existing_profile(ssid)
        if existing_profile:
            logger.info(f"[WiFi] Found existing profile '{existing_profile}'. Updating and activating...")
            if password:
                _run_nmcli(
                    [
                        "connection", "modify", existing_profile,
                        "wifi-sec.key-mgmt", "wpa-psk",
                        "wifi-sec.psk", password,
                    ],
                    timeout=5,
                    check=False,
                )
            res = _run_nmcli(["connection", "up", "id", existing_profile], timeout=20, check=False)
        else:
            logger.info(f"[WiFi] No existing profile for '{ssid}'. Creating new connection...")
            cmd = ["dev", "wifi", "connect", ssid]
            if password:
                cmd.extend(["password", password])
            res = _run_nmcli(cmd, timeout=20, check=False)

        if res.returncode == 0:
            logger.info(f"[WiFi] Successfully connected to Wi-Fi: '{ssid}'!")
            stop_emergency_hotspot()
            return True, f"Successfully connected to Wi-Fi: '{ssid}'."
        else:
            err_msg = res.stderr.strip() or res.stdout.strip() or "Connection failed"
            logger.warning(f"[WiFi] Failed to connect to '{ssid}': {err_msg}")
            # Re-engage emergency hotspot so technician does not lose connection
            start_emergency_hotspot()
            return False, f"Failed to connect to '{ssid}': {err_msg}"
    except (subprocess.SubprocessError, OSError) as e:
        logger.error(f"[WiFi] Subprocess error connecting to '{ssid}': {e}")
        start_emergency_hotspot()
        return False, f"System error connecting to Wi-Fi: {e}"


def _watchdog_loop(interval: float):
    """Monitors Wi-Fi connection and triggers emergency hotspot if disconnected."""
    logger.info(f"[WiFi Watchdog] Started network monitoring (check interval: {interval}s).")
    while not _watchdog_stop_event.is_set():
        if not is_wifi_connected():
            if not is_hotspot_active():
                logger.warning("[WiFi Watchdog] No active Wi-Fi connection detected! Starting emergency hotspot...")
                start_emergency_hotspot()
        else:
            if is_hotspot_active():
                logger.info("[WiFi Watchdog] Wi-Fi connection restored. Stopping emergency hotspot.")
                stop_emergency_hotspot()

        _watchdog_stop_event.wait(interval)

    logger.info("[WiFi Watchdog] Stopped network monitoring.")


def start_wifi_watchdog(interval: float = DEFAULT_WIFI_WATCHDOG_INTERVAL):
    """Starts the background Wi-Fi monitoring thread."""
    global _watchdog_thread
    if _watchdog_thread and _watchdog_thread.is_alive():
        return

    _watchdog_stop_event.clear()
    _watchdog_thread = threading.Thread(
        target=_watchdog_loop,
        args=(interval,),
        name="WiFiWatchdog",
        daemon=True,
    )
    _watchdog_thread.start()


def stop_wifi_watchdog():
    """Stops the background Wi-Fi monitoring thread."""
    _watchdog_stop_event.set()


__all__ = [
    "DEFAULT_HOTSPOT_PASS",
    "DEFAULT_HOTSPOT_SSID",
    "HOTSPOT_CON_NAME",
    "connect_to_wifi",
    "get_existing_profile",
    "get_wifi_interface",
    "is_hotspot_active",
    "is_nmcli_available",
    "is_wifi_connected",
    "start_emergency_hotspot",
    "start_wifi_watchdog",
    "stop_emergency_hotspot",
    "stop_wifi_watchdog",
]
