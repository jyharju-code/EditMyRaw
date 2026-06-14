"""raw_io.py — load RAW/JPEG, build previews, export JPEG / 16-bit TIFF."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

RAW_EXTENSIONS = {".arw", ".raw", ".dng", ".cr2", ".cr3", ".nef", ".raf", ".orf", ".rw2", ".pef", ".srw"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}
SUPPORTED_EXTENSIONS = RAW_EXTENSIONS | IMAGE_EXTENSIONS


def is_supported(path: Path | str) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def load_image(path: Path | str) -> Image.Image:
    path = Path(path)
    if path.suffix.lower() in RAW_EXTENSIONS:
        return _load_raw(path)
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def _load_raw(path: Path) -> Image.Image:
    try:
        import rawpy
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("RAW support requires rawpy (`pip install rawpy`).") from exc
    with rawpy.imread(str(path)) as raw:
        rgb = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            output_bps=8,
            gamma=(2.222, 4.5),
            demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
        )
    return Image.fromarray(rgb).convert("RGB")


def make_preview(image: Image.Image, max_side: int = 1280) -> Image.Image:
    preview = image.copy()
    preview.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return preview.convert("RGB")


def save_image(image: Image.Image, path: Path | str, fmt: str = "jpg", quality: int = 95) -> Path:
    """fmt: 'jpg' (8-bit) or 'tiff' (16-bit container). Returns the written path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rgb = image.convert("RGB")
    if fmt == "tiff":
        import cv2
        arr8 = np.asarray(rgb)
        arr16 = (arr8.astype(np.float32) / 255.0 * 65535.0 + 0.5).astype(np.uint16)
        cv2.imwrite(str(path), arr16[..., ::-1])  # cv2 expects BGR
    else:
        rgb.save(path, "JPEG", quality=int(quality), optimize=True, progressive=True)
    return path


def pil_to_bgr(image: Image.Image) -> np.ndarray:
    return np.array(image.convert("RGB"))[:, :, ::-1].copy()


def bgr_to_pil(array: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(array[:, :, ::-1], 0, 255).astype("uint8"), "RGB")
