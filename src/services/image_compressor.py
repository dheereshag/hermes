"""image_compressor.py — High-clarity JPEG compression for fleet camera captures."""
from __future__ import annotations

import cv2
import numpy as np


def compress_image_bytes(
    image_bytes: bytes | None,
    max_dim: int = 1920,
    quality: int = 85,
) -> bytes | None:
    """Downscale to max_dim if larger and compress as high-clarity JPEG."""
    if not image_bytes:
        return None
    try:
        buf = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes

        h, w = img.shape[:2]
        if max(h, w) <= max_dim and len(image_bytes) <= 450_000:
            return image_bytes

        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            new_w = max(1, round(w * scale))
            new_h = max(1, round(h * scale))
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        params = [
            int(cv2.IMWRITE_JPEG_QUALITY),
            int(quality),
            int(cv2.IMWRITE_JPEG_OPTIMIZE),
            1,
        ]
        ok, encoded = cv2.imencode(".jpg", img, params)
        if ok and encoded is not None:
            return encoded.tobytes()
        return image_bytes
    except (cv2.error, ValueError, TypeError, OSError):
        return image_bytes
