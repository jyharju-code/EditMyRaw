"""skin.py — face/skin weight maps so look-matching prioritizes skin tones."""

from __future__ import annotations

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except Exception:  # pragma: no cover
    HAS_CV2 = False

_cascade = None


def _u8(rgb: np.ndarray) -> np.ndarray:
    return np.clip(rgb, 0, 255).astype(np.uint8)


def detect_faces(rgb_u8: np.ndarray) -> list[tuple[int, int, int, int]]:
    global _cascade
    if not HAS_CV2:
        return []
    if _cascade is None:
        _cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    gray = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2GRAY)
    m = max(24, int(0.06 * min(gray.shape[:2])))
    faces = _cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(m, m))
    return [tuple(int(v) for v in f) for f in faces]


def skin_mask(rgb_u8: np.ndarray) -> np.ndarray:
    if not HAS_CV2:
        r, g, b = rgb_u8[..., 0], rgb_u8[..., 1], rgb_u8[..., 2]
        return (r > 90) & (r > g) & (g > b * 0.9) & ((r.astype(int) - b) > 12)
    ycc = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2YCrCb)
    Cr = ycc[..., 1].astype(int)
    Cb = ycc[..., 2].astype(int)
    return (Cr >= 135) & (Cr <= 180) & (Cb >= 85) & (Cb <= 135)


def weight_map(rgb_u8: np.ndarray, mode: str) -> tuple[np.ndarray, str]:
    """mode: 'none' | 'skin' | 'face'. Returns (weights 0..1, short info string)."""
    rgb_u8 = _u8(rgb_u8)
    h, w = rgb_u8.shape[:2]
    if mode == "none":
        return np.ones((h, w), np.float32), "whole image"
    skin = skin_mask(rgb_u8)
    if mode == "skin":
        if skin.mean() < 0.005:
            return np.ones((h, w), np.float32), "no skin -> whole image"
        return (0.15 + 0.85 * skin).astype(np.float32), f"skin {skin.mean()*100:.0f}%"
    faces = detect_faces(rgb_u8)
    if not faces:
        if skin.mean() > 0.02:
            return (0.15 + 0.85 * skin).astype(np.float32), "no face -> skin"
        return np.ones((h, w), np.float32), "no face -> whole image"
    facemask = np.zeros((h, w), np.float32)
    for (x, y, fw, fh) in faces:
        x0, y0 = max(0, int(x - 0.1 * fw)), max(0, int(y - 0.15 * fh))
        x1, y1 = min(w, int(x + 1.1 * fw)), min(h, int(y + 1.2 * fh))
        facemask[y0:y1, x0:x1] = 1.0
    wmap = 0.1 + 0.45 * facemask + 0.45 * (facemask * skin)
    return np.clip(wmap, 0, 1).astype(np.float32), f"{len(faces)} face(s)"
