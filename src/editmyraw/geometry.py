"""geometry.py — proportion/geometry corrections: rotation, lens, perspective, region scaling, crop."""

from __future__ import annotations

import math

import cv2
import numpy as np
from PIL import Image, ImageFilter

from .raw_io import bgr_to_pil, pil_to_bgr
from .recipe import BBox, Recipe


def apply_geometry(image: Image.Image, recipe: Recipe) -> Image.Image:
    current = image.convert("RGB")
    current = _rotate(current, recipe.corrections.rotation_degrees)
    current = _radial(current, recipe.corrections.lens_distortion)
    current = _perspective(current, recipe.corrections.vertical_perspective,
                           recipe.corrections.horizontal_perspective)
    current = _scale_region(current, recipe.subject_bbox,
                            recipe.corrections.subject_width_scale,
                            recipe.corrections.subject_height_scale, feather=0.18)
    if recipe.face_bbox is not None:
        current = _scale_region(current, recipe.face_bbox,
                                recipe.corrections.face_width_scale, 1.0, feather=0.28)
    if recipe.corrections.upper_body_scale != 1.0:
        current = _scale_region(current, _upper_body_bbox(recipe.subject_bbox),
                                recipe.corrections.upper_body_scale, 1.0, feather=0.25)
    return _crop_to_ratio(current, recipe.corrections.crop_ratio)


def _rotate(image: Image.Image, degrees: float) -> Image.Image:
    if abs(degrees) < 0.05:
        return image
    return image.rotate(degrees, resample=Image.Resampling.BICUBIC, expand=False)


def _radial(image: Image.Image, amount: float) -> Image.Image:
    if abs(amount) < 0.001:
        return image
    src = pil_to_bgr(image)
    h, w = src.shape[:2]
    cam = np.array([[w, 0, w / 2.0], [0, w, h / 2.0], [0, 0, 1]], dtype=np.float32)
    dist = np.array([amount, 0.0, 0.0, 0.0], dtype=np.float32)
    newcam = cv2.getOptimalNewCameraMatrix(cam, dist, (w, h), alpha=0.0)[0]
    return bgr_to_pil(cv2.undistort(src, cam, dist, None, newcam))


def _perspective(image: Image.Image, vertical: float, horizontal: float) -> Image.Image:
    if abs(vertical) < 0.001 and abs(horizontal) < 0.001:
        return image
    src = pil_to_bgr(image)
    h, w = src.shape[:2]
    v, hh = vertical * w, horizontal * h
    src_pts = np.float32([
        [0 + max(v, 0), 0 + max(hh, 0)],
        [w - max(-v, 0), 0 + max(-hh, 0)],
        [w - max(v, 0), h - max(hh, 0)],
        [0 + max(-v, 0), h - max(-hh, 0)],
    ])
    dst_pts = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(src, matrix, (w, h), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REFLECT_101)
    return bgr_to_pil(warped)


def _scale_region(image: Image.Image, bbox: BBox, sx: float, sy: float, feather: float) -> Image.Image:
    if abs(sx - 1.0) < 0.005 and abs(sy - 1.0) < 0.005:
        return image
    w, h = image.size
    left, top = int(w * bbox.left), int(h * bbox.top)
    right, bottom = int(w * bbox.right), int(h * bbox.bottom)
    if right - left < 8 or bottom - top < 8:
        return image
    region = image.crop((left, top, right, bottom))
    rw, rh = region.size
    sw, sh = max(1, int(rw * sx)), max(1, int(rh * sy))
    scaled = region.resize((sw, sh), Image.Resampling.BICUBIC)
    canvas = Image.new("RGB", image.size)
    canvas.paste(image)
    px, py = left + (rw - sw) // 2, top + (rh - sh) // 2
    canvas.paste(scaled, (px, py))
    mask = Image.new("L", image.size, 0)
    local = Image.new("L", (sw, sh), 255).filter(
        ImageFilter.GaussianBlur(max(2, int(min(rw, rh) * feather))))
    mask.paste(local, (px, py))
    return Image.composite(canvas, image, mask)


def _upper_body_bbox(bbox: BBox) -> BBox:
    height = bbox.bottom - bbox.top
    return BBox(left=max(0.0, bbox.left - 0.03), top=bbox.top + height * 0.18,
               right=min(1.0, bbox.right + 0.03), bottom=bbox.top + height * 0.62)


def _crop_to_ratio(image: Image.Image, ratio: str) -> Image.Image:
    if ratio == "original":
        return image
    target = _parse_ratio(ratio)
    if target is None:
        return image
    w, h = image.size
    current = w / h
    if math.isclose(current, target, rel_tol=0.01):
        return image
    if current > target:
        new_w = int(h * target)
        left = (w - new_w) // 2
        return image.crop((left, 0, left + new_w, h))
    new_h = int(w / target)
    top = (h - new_h) // 2
    return image.crop((0, top, w, top + new_h))


def _parse_ratio(ratio: str) -> float | None:
    if ":" not in ratio:
        return None
    a, b = ratio.split(":", 1)
    try:
        num, den = float(a), float(b)
    except ValueError:
        return None
    return num / den if den else None
