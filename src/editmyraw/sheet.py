"""sheet.py — tile candidate previews into one image for the consistency critic."""

from __future__ import annotations

from PIL import Image


def _thumb(img: Image.Image, w: int) -> Image.Image:
    h = max(1, int(img.height * w / img.width))
    return img.convert("RGB").resize((w, h), Image.Resampling.LANCZOS)


def tile_previews(previews, cols: int = 3, cell_w: int = 300) -> Image.Image:
    thumbs = [_thumb(p, cell_w) for p in previews]
    if not thumbs:
        return Image.new("RGB", (cell_w, cell_w), (30, 30, 34))
    cell_h = max(t.height for t in thumbs)
    rows = (len(thumbs) + cols - 1) // cols
    pad = 8
    width = cols * cell_w + (cols + 1) * pad
    height = rows * (cell_h + pad) + pad
    sheet = Image.new("RGB", (width, height), (30, 30, 34))
    for i, t in enumerate(thumbs):
        r, c = divmod(i, cols)
        sheet.paste(t, (pad + c * (cell_w + pad), pad + r * (cell_h + pad)))
    return sheet
