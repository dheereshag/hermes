"""
camera.py — IP Camera Frame Grabber & Parallel Snapshot Driver
==============================================================
Low-resource IP camera frame capture module.
Supports HTTP JPEG Snapshots and on-demand OpenCV RTSP stream frame grabbing.
Uses ThreadPoolExecutor for concurrent multi-camera snapshot capture.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from src.config import config
from src.config.constants import (
    CAMERA_TIMEOUT,
    MAX_PARALLEL_CAMERA_WORKERS,
)

logger = logging.getLogger(__name__)


def fetch_image_bytes(camera_url: str, timeout: float = CAMERA_TIMEOUT) -> bytes | None:
    """
    Fetch raw JPEG image bytes from a camera URL.
    Prefers HTTP JPEG Snapshots for low CPU/RAM footprint.
    Falls back to on-demand OpenCV RTSP single-frame capture if URL starts with 'rtsp://'.
    """
    if not camera_url:
        return None

    if camera_url.lower().startswith("rtsp://"):
        return _fetch_rtsp_frame(camera_url, timeout)
    else:
        return _fetch_http_snapshot(camera_url, timeout)


def _fetch_http_snapshot(url: str, timeout: float) -> bytes | None:
    """Fetch HTTP JPEG snapshot with low memory footprint."""
    try:
        # verify=False handles cameras with self-signed SSL certificates
        response = requests.get(url, timeout=timeout, verify=False)
        if response.status_code == 200 and response.content:
            return response.content
        else:
            logger.warning(f"[Camera] HTTP fetch failed for {url}: Status {response.status_code}")
            return None
    except requests.RequestException as e:
        logger.error(f"[Camera] Exception fetching snapshot from {url}: {e}")
        return None


def _fetch_rtsp_frame(rtsp_url: str, timeout: float) -> bytes | None:
    """On-demand single frame capture from RTSP stream using OpenCV."""
    try:
        import cv2

        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            logger.warning(f"[Camera] Unable to open RTSP stream: {rtsp_url}")
            return None

        # Set low buffer size if supported
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ret, frame = cap.read()
        cap.release()

        if ret and frame is not None:
            # Encode frame to JPEG byte buffer in RAM
            success, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if success:
                return buffer.tobytes()
        logger.warning(f"[Camera] Failed to read frame from RTSP stream: {rtsp_url}")
        return None
    except (cv2.error, OSError, ValueError, ImportError) as e:
        logger.error(f"[Camera] OpenCV RTSP exception for {rtsp_url}: {e}")
        return None


def capture_auxiliary_snapshots(
    camera_urls: list[str] | None = None,
) -> dict[int, bytes | None]:
    """
    Concurrently captures snapshot images from all auxiliary cameras (Cameras 2 ... N).
    Returns a dict mapping camera_index (2, 3, ...) to raw image bytes or None.
    """
    urls = camera_urls if camera_urls is not None else config.auxiliary_camera_urls
    results: dict[int, bytes | None] = {}

    if not urls:
        logger.info("[Camera] No auxiliary cameras configured. Skipping parallel capture.")
        return results

    logger.info(f"[Camera] Triggering parallel snapshot capture for {len(urls)} auxiliary cameras...")
    start_time = time.time()

    workers = min(len(urls), MAX_PARALLEL_CAMERA_WORKERS)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Map future to camera index (starting at index 2)
        future_to_idx = {
            executor.submit(fetch_image_bytes, url): idx + 2
            for idx, url in enumerate(urls)
        }

        for future in as_completed(future_to_idx):
            cam_idx = future_to_idx[future]
            try:
                img_bytes = future.result()
                results[cam_idx] = img_bytes
                status = "SUCCESS" if img_bytes else "FAILED"
                logger.info(f"[Camera] Camera {cam_idx} snapshot capture: {status}")
            except (requests.RequestException, OSError, ValueError, RuntimeError) as exc:
                logger.error(f"[Camera] Camera {cam_idx} snapshot generated exception: {exc}")
                results[cam_idx] = None

    elapsed = time.time() - start_time
    logger.info(f"[Camera] Auxiliary parallel capture completed in {elapsed:.2f}s")
    return results


def capture_anpr_snapshots(
    camera_urls: list[str] | None = None,
) -> list[tuple[int, str, bytes | None]]:
    """
    Concurrently captures snapshot images from all configured ANPR cameras (e.g. Front, Rear).
    Returns a list of tuples: (camera_index, camera_url, image_bytes_or_none).
    Camera index is 1-based (1 for Front ANPR, 2 for Rear ANPR, etc.)
    """
    urls = camera_urls if camera_urls is not None else config.anpr_camera_urls
    if not urls:
        return []

    if len(urls) == 1:
        img_bytes = fetch_image_bytes(urls[0])
        return [(1, urls[0], img_bytes)]

    workers = min(len(urls), MAX_PARALLEL_CAMERA_WORKERS)
    results_dict: dict[int, bytes | None] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {
            executor.submit(fetch_image_bytes, url): idx + 1
            for idx, url in enumerate(urls)
        }
        for future in as_completed(future_to_idx):
            cam_idx = future_to_idx[future]
            try:
                results_dict[cam_idx] = future.result()
            except (requests.RequestException, OSError, ValueError, RuntimeError) as exc:
                logger.error(f"[Camera] ANPR Camera {cam_idx} generated exception: {exc}")
                results_dict[cam_idx] = None

    return [(idx + 1, url, results_dict.get(idx + 1)) for idx, url in enumerate(urls)]


def capture_all_camera_snapshots(
    anpr_urls: list[str] | None = None,
    aux_urls: list[str] | None = None,
) -> dict[str, bytes | None]:
    """
    Concurrently captures snapshots from all cameras (all ANPR + all Auxiliary).
    Returns a dict mapping canonical labels ('anpr_1', 'anpr_2', 'aux_1', 'aux_2', etc.)
    to raw JPEG bytes or None.
    """
    a_urls = anpr_urls if anpr_urls is not None else config.anpr_camera_urls
    x_urls = aux_urls if aux_urls is not None else config.auxiliary_camera_urls

    labeled_tasks: list[tuple[str, str]] = []
    for idx, url in enumerate(a_urls):
        labeled_tasks.append((f"anpr_{idx + 1}", url))
    for idx, url in enumerate(x_urls):
        labeled_tasks.append((f"aux_{idx + 1}", url))

    if not labeled_tasks:
        return {}

    workers = min(len(labeled_tasks), MAX_PARALLEL_CAMERA_WORKERS)
    results: dict[str, bytes | None] = {}
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_label = {
            executor.submit(fetch_image_bytes, url): label
            for label, url in labeled_tasks
        }
        for future in as_completed(future_to_label):
            label = future_to_label[future]
            try:
                img_bytes = future.result()
                results[label] = img_bytes
                status = "SUCCESS" if img_bytes else "FAILED"
                logger.info(f"[Camera] Full fleet {label} capture: {status}")
            except (requests.RequestException, OSError, ValueError, RuntimeError) as exc:
                logger.error(f"[Camera] {label} snapshot generated exception: {exc}")
                results[label] = None

    elapsed = time.time() - start_time
    logger.info(f"[Camera] Full fleet capture ({len(labeled_tasks)} cameras) completed in {elapsed:.2f}s")
    return results


def log_camera_fleet() -> None:
    """Logs the configured main (ANPR) and auxiliary camera fleet at startup."""
    anpr_urls = config.anpr_camera_urls
    aux_urls = config.auxiliary_camera_urls

    logger.info("[Cameras] Configured Camera Fleet:")
    if anpr_urls:
        logger.info(f"  ├── Main / ANPR Cameras ({len(anpr_urls)} configured - active loop):")
        for idx, url in enumerate(anpr_urls):
            prefix = "└──" if idx == len(anpr_urls) - 1 and not aux_urls else "├──"
            logger.info(f"  │     {prefix} [Cam {idx + 1} - ANPR] {url}")
    else:
        logger.warning("  ├── Main / ANPR Cameras: (None configured)")

    if aux_urls:
        logger.info(f"  └── Auxiliary Cameras ({len(aux_urls)} configured - post-stability audit):")
        for idx, url in enumerate(aux_urls):
            prefix = "└──" if idx == len(aux_urls) - 1 else "├──"
            logger.info(f"        {prefix} [Aux {idx + 1}] {url}")
    else:
        logger.info("  └── Auxiliary Cameras: (None configured)")


__all__ = [
    "capture_all_camera_snapshots",
    "capture_anpr_snapshots",
    "capture_auxiliary_snapshots",
    "fetch_image_bytes",
    "log_camera_fleet",
]
