"""
style.py — reference look profile + transfer, with optional skin weighting.

build_look_profile() summarizes a reference image's color/luma/saturation.
apply_look_profile() pulls a target toward that profile (Reinhard-style Lab
transfer + luma histogram blend). When skin_mode != 'none', the color/exposure
center (Lab mean/std) is computed from skin/face pixels so skin tones match.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .skin import weight_map


@dataclass(frozen=True)
class LookProfile:
    lab_mean: list
    lab_std: list
    luma_percentiles: list
    luma_values: list
    hsv_saturation_mean: float
    hsv_value_mean: float
    skin_info: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "LookProfile":
        return cls(**json.loads(text))


def _rgb_array(image: Image.Image, max_side: int | None = 1800) -> np.ndarray:
    working = image.convert("RGB")
    if max_side is not None:
        working.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return np.array(working, dtype=np.uint8)


def _weighted_mean_std(values: np.ndarray, w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """values: (N,3) float, w: (N,) float."""
    wsum = float(w.sum())
    if wsum < 1e-6:
        w = np.ones_like(w)
        wsum = float(w.sum())
    mean = (values * w[:, None]).sum(axis=0) / wsum
    var = (w[:, None] * (values - mean) ** 2).sum(axis=0) / wsum
    return mean, np.maximum(np.sqrt(var), 1.0)


def build_look_profile(reference: Image.Image, skin_mode: str = "face") -> LookProfile:
    rgb = _rgb_array(reference, max_side=1800)
    weights, info = weight_map(rgb, skin_mode)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    w = weights.reshape(-1)
    lab_mean, lab_std = _weighted_mean_std(lab.reshape(-1, 3), w)
    percentiles = list(np.linspace(0, 100, 33))
    luma = lab[:, :, 0].reshape(-1)
    return LookProfile(
        lab_mean=[float(x) for x in lab_mean],
        lab_std=[float(x) for x in lab_std],
        luma_percentiles=[float(x) for x in percentiles],
        luma_values=[float(x) for x in np.percentile(luma, percentiles)],
        hsv_saturation_mean=float(hsv[:, :, 1].mean()),
        hsv_value_mean=float(hsv[:, :, 2].mean()),
        skin_info=info,
    )


def apply_look_profile(image: Image.Image, profile: LookProfile,
                       strength: float = 0.85, skin_mode: str = "face") -> Image.Image:
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength <= 0.001:
        return image.convert("RGB")
    rgb = _rgb_array(image, max_side=None)
    weights, _ = weight_map(rgb, skin_mode)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    flat = lab.reshape(-1, 3)
    src_mean, src_std = _weighted_mean_std(flat, weights.reshape(-1))
    ref_mean = np.array(profile.lab_mean, dtype=np.float32)
    ref_std = np.array(profile.lab_std, dtype=np.float32)

    matched = (lab - src_mean) / src_std * ref_std + ref_mean
    lab = lab * (1.0 - strength) + matched * strength
    lab[:, :, 0] = _blend_luma_histogram(lab[:, :, 0], profile, strength * 0.75)
    lab = np.clip(lab, 0, 255).astype(np.uint8)
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB).astype(np.float32)
    out = _match_saturation_value(out, profile, strength * 0.45)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def _blend_luma_histogram(luma: np.ndarray, profile: LookProfile, strength: float) -> np.ndarray:
    if strength <= 0.001:
        return luma
    percentiles = np.array(profile.luma_percentiles, dtype=np.float32)
    src_values = np.percentile(luma.reshape(-1), percentiles)
    ref_values = np.array(profile.luma_values, dtype=np.float32)
    src_values = np.maximum.accumulate(src_values)
    for i in range(1, len(src_values)):
        if src_values[i] <= src_values[i - 1]:
            src_values[i] = src_values[i - 1] + 1e-3
    mapped = np.interp(luma.reshape(-1), src_values, ref_values).reshape(luma.shape)
    return luma * (1.0 - strength) + mapped * strength


def _match_saturation_value(rgb: np.ndarray, profile: LookProfile, strength: float) -> np.ndarray:
    if strength <= 0.001:
        return rgb
    hsv = cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    cur_sat = max(float(hsv[:, :, 1].mean()), 1.0)
    cur_val = max(float(hsv[:, :, 2].mean()), 1.0)
    sat_scale = (profile.hsv_saturation_mean / cur_sat - 1.0) * strength + 1.0
    val_scale = (profile.hsv_value_mean / cur_val - 1.0) * strength + 1.0
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * sat_scale, 0, 255)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] * val_scale, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32)
