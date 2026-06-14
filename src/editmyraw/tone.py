"""tone.py — apply tonal/color adjustments from a recipe (exposure, contrast, color, etc.)."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from .recipe import ToneAdjustments


def apply_tone(image: Image.Image, tone: ToneAdjustments) -> Image.Image:
    current = image.convert("RGB")
    current = _exposure_and_range(current, tone)
    current = _color_balance(current, tone)
    if abs(tone.contrast) > 0.005:
        current = ImageEnhance.Contrast(current).enhance(max(0.05, 1.0 + tone.contrast))
    if abs(tone.saturation - 1.0) > 0.005:
        current = ImageEnhance.Color(current).enhance(max(0.0, tone.saturation))
    if abs(tone.clarity) > 0.005:
        current = _clarity(current, tone.clarity)
    if abs(tone.vignette) > 0.005:
        current = _vignette(current, tone.vignette)
    return current


def _exposure_and_range(image: Image.Image, tone: ToneAdjustments) -> Image.Image:
    arr = np.array(image, dtype=np.float32) / 255.0
    if abs(tone.exposure_ev) > 0.005:
        arr *= 2.0 ** tone.exposure_ev
    luma = (arr[:, :, 0] * 0.2126 + arr[:, :, 1] * 0.7152 + arr[:, :, 2] * 0.0722)[:, :, None]
    if abs(tone.shadows) > 0.005:
        arr += np.clip(1.0 - luma * 1.35, 0.0, 1.0) * tone.shadows * 0.28
    if abs(tone.highlights) > 0.005:
        arr += np.clip((luma - 0.45) / 0.55, 0.0, 1.0) * tone.highlights * 0.25
    return Image.fromarray(np.clip(arr * 255.0, 0, 255).astype(np.uint8), "RGB")


def _color_balance(image: Image.Image, tone: ToneAdjustments) -> Image.Image:
    if abs(tone.temperature) < 0.005 and abs(tone.tint) < 0.005:
        return image
    arr = np.array(image, dtype=np.float32)
    temp, tint = tone.temperature, tone.tint
    arr[:, :, 0] *= 1.0 + temp * 0.10 + tint * 0.03
    arr[:, :, 1] *= 1.0 - tint * 0.08
    arr[:, :, 2] *= 1.0 - temp * 0.10 + tint * 0.03
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def _clarity(image: Image.Image, clarity: float) -> Image.Image:
    arr = np.array(image, dtype=np.float32)
    blurred = np.array(image.filter(ImageFilter.GaussianBlur(radius=2.0)), dtype=np.float32)
    out = arr + (arr - blurred) * (clarity * 0.85)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def _vignette(image: Image.Image, vignette: float) -> Image.Image:
    arr = np.array(image, dtype=np.float32) / 255.0
    h, w = arr.shape[:2]
    y, x = np.ogrid[:h, :w]
    cx, cy = w / 2.0, h / 2.0
    dist = np.clip(np.sqrt(((x - cx) / cx) ** 2 + ((y - cy) / cy) ** 2), 0.0, 1.0)[:, :, None]
    factor = 1.0 + vignette * (0.55 if vignette < 0 else 0.35) * dist
    return Image.fromarray(np.clip(arr * factor * 255.0, 0, 255).astype(np.uint8), "RGB")
