"""recipe.py — the bounded editing recipe (tone + geometry/proportion + crop)."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Mode(str, Enum):
    faithful = "faithful"
    creative = "creative"


class BBox(BaseModel):
    """Normalized bounding box, left/top/right/bottom in 0..1."""

    left: float = Field(0.15, ge=0.0, le=1.0)
    top: float = Field(0.05, ge=0.0, le=1.0)
    right: float = Field(0.85, ge=0.0, le=1.0)
    bottom: float = Field(0.95, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def ensure_valid_order(self) -> "BBox":
        if self.right <= self.left:
            self.right = min(1.0, self.left + 0.1)
        if self.bottom <= self.top:
            self.bottom = min(1.0, self.top + 0.1)
        return self


class Corrections(BaseModel):
    lens_distortion: float = Field(0.0, ge=-0.18, le=0.18,
                                   description="Radial correction; negative reduces barrel distortion.")
    vertical_perspective: float = Field(0.0, ge=-0.22, le=0.22)
    horizontal_perspective: float = Field(0.0, ge=-0.18, le=0.18)
    rotation_degrees: float = Field(0.0, ge=-6.0, le=6.0)
    subject_width_scale: float = Field(1.0, ge=0.82, le=1.18)
    subject_height_scale: float = Field(1.0, ge=0.88, le=1.12)
    face_width_scale: float = Field(1.0, ge=0.86, le=1.14)
    upper_body_scale: float = Field(1.0, ge=0.86, le=1.14)
    crop_ratio: str = Field("original", description="original, 1:1, 4:5, 3:2, 16:9, or 9:16")
    confidence: float = Field(0.5, ge=0.0, le=1.0)

    @field_validator("crop_ratio")
    @classmethod
    def normalize_crop_ratio(cls, value: str) -> str:
        normalized = value.strip().lower()
        return normalized if normalized in {"original", "1:1", "4:5", "3:2", "16:9", "9:16"} else "original"


class ToneAdjustments(BaseModel):
    exposure_ev: float = Field(0.0, ge=-2.0, le=2.0)
    contrast: float = Field(0.0, ge=-1.0, le=1.0)
    highlights: float = Field(0.0, ge=-1.0, le=1.0)
    shadows: float = Field(0.0, ge=-1.0, le=1.0)
    saturation: float = Field(1.0, ge=0.0, le=2.2)
    temperature: float = Field(0.0, ge=-1.0, le=1.0)
    tint: float = Field(0.0, ge=-1.0, le=1.0)
    clarity: float = Field(0.0, ge=-1.0, le=1.0)
    vignette: float = Field(0.0, ge=-1.0, le=1.0)
    style_match_strength: float = Field(0.85, ge=0.0, le=1.0)


class Recipe(BaseModel):
    mode: Mode = Mode.faithful
    diagnosis: str = ""
    subject_bbox: BBox = Field(default_factory=BBox)
    face_bbox: Optional[BBox] = None
    corrections: Corrections = Field(default_factory=Corrections)
    tone: ToneAdjustments = Field(default_factory=ToneAdjustments)
    creative_generate: bool = False

    def bounded_for_mode(self, mode: Mode) -> "Recipe":
        data = self.model_dump()
        data["mode"] = mode.value
        recipe = Recipe.model_validate(data)
        c, t = recipe.corrections, recipe.tone
        if mode == Mode.faithful:
            c.lens_distortion = clamp(c.lens_distortion, -0.08, 0.08)
            c.vertical_perspective = clamp(c.vertical_perspective, -0.10, 0.10)
            c.horizontal_perspective = clamp(c.horizontal_perspective, -0.08, 0.08)
            c.rotation_degrees = clamp(c.rotation_degrees, -3.0, 3.0)
            c.subject_width_scale = clamp(c.subject_width_scale, 0.92, 1.08)
            c.subject_height_scale = clamp(c.subject_height_scale, 0.94, 1.06)
            c.face_width_scale = clamp(c.face_width_scale, 0.92, 1.08)
            c.upper_body_scale = clamp(c.upper_body_scale, 0.92, 1.08)
            t.exposure_ev = clamp(t.exposure_ev, -0.8, 0.8)
            t.contrast = clamp(t.contrast, -0.45, 0.45)
            t.highlights = clamp(t.highlights, -0.65, 0.65)
            t.shadows = clamp(t.shadows, -0.65, 0.65)
            t.saturation = clamp(t.saturation, 0.55, 1.55)
            t.temperature = clamp(t.temperature, -0.55, 0.55)
            t.tint = clamp(t.tint, -0.45, 0.45)
            t.clarity = clamp(t.clarity, -0.35, 0.45)
            t.vignette = clamp(t.vignette, -0.45, 0.45)
            t.style_match_strength = clamp(t.style_match_strength, 0.0, 0.9)
            recipe.creative_generate = False
        else:
            c.lens_distortion = clamp(c.lens_distortion, -0.16, 0.16)
            c.vertical_perspective = clamp(c.vertical_perspective, -0.20, 0.20)
            c.horizontal_perspective = clamp(c.horizontal_perspective, -0.16, 0.16)
            c.rotation_degrees = clamp(c.rotation_degrees, -5.0, 5.0)
            c.subject_width_scale = clamp(c.subject_width_scale, 0.86, 1.14)
            c.subject_height_scale = clamp(c.subject_height_scale, 0.90, 1.10)
            c.face_width_scale = clamp(c.face_width_scale, 0.88, 1.12)
            c.upper_body_scale = clamp(c.upper_body_scale, 0.88, 1.12)
            t.exposure_ev = clamp(t.exposure_ev, -1.4, 1.4)
            t.contrast = clamp(t.contrast, -0.75, 0.75)
            t.highlights = clamp(t.highlights, -0.9, 0.9)
            t.shadows = clamp(t.shadows, -0.9, 0.9)
            t.saturation = clamp(t.saturation, 0.25, 1.95)
            t.temperature = clamp(t.temperature, -0.85, 0.85)
            t.tint = clamp(t.tint, -0.7, 0.7)
            t.clarity = clamp(t.clarity, -0.65, 0.75)
            t.vignette = clamp(t.vignette, -0.75, 0.75)
            t.style_match_strength = clamp(t.style_match_strength, 0.0, 1.0)
        return recipe


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def neutral_recipe(mode: Mode = Mode.faithful, prompt: str = "") -> Recipe:
    diagnosis = "Neutral recipe (no Gemini call)."
    if prompt:
        diagnosis += f" Prompt noted: {prompt[:180]}"
    return Recipe(mode=mode, diagnosis=diagnosis).bounded_for_mode(mode)
