"""
gemini.py — Gemini as an advisor (recipe) and optional generative editor.

- analyze() / analyze_with_reference(): vision -> bounded JSON recipe.
- creative_edit(): optional generative pixel edit (Creative mode only).
- consistency_deltas(): batch "sparring" critic that nudges a whole set toward
  the reference and toward each other (runs hidden, multiple rounds).

Uses the official google-genai SDK. The API key comes from config (GUI/env),
never hardcoded.
"""

from __future__ import annotations

import json
from io import BytesIO

from PIL import Image

from .config import Settings
from .recipe import Mode, Recipe

RECIPE_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["faithful", "creative"]},
        "diagnosis": {"type": "string"},
        "subject_bbox": {"type": "object", "properties": {
            "left": {"type": "number"}, "top": {"type": "number"},
            "right": {"type": "number"}, "bottom": {"type": "number"}},
            "required": ["left", "top", "right", "bottom"]},
        "face_bbox": {"anyOf": [{"type": "null"}, {"type": "object", "properties": {
            "left": {"type": "number"}, "top": {"type": "number"},
            "right": {"type": "number"}, "bottom": {"type": "number"}},
            "required": ["left", "top", "right", "bottom"]}]},
        "corrections": {"type": "object", "properties": {
            "lens_distortion": {"type": "number"}, "vertical_perspective": {"type": "number"},
            "horizontal_perspective": {"type": "number"}, "rotation_degrees": {"type": "number"},
            "subject_width_scale": {"type": "number"}, "subject_height_scale": {"type": "number"},
            "face_width_scale": {"type": "number"}, "upper_body_scale": {"type": "number"},
            "crop_ratio": {"type": "string"}, "confidence": {"type": "number"}},
            "required": ["lens_distortion", "vertical_perspective", "horizontal_perspective",
                         "rotation_degrees", "subject_width_scale", "subject_height_scale",
                         "face_width_scale", "upper_body_scale", "crop_ratio", "confidence"]},
        "tone": {"type": "object", "properties": {
            "exposure_ev": {"type": "number"}, "contrast": {"type": "number"},
            "highlights": {"type": "number"}, "shadows": {"type": "number"},
            "saturation": {"type": "number"}, "temperature": {"type": "number"},
            "tint": {"type": "number"}, "clarity": {"type": "number"},
            "vignette": {"type": "number"}, "style_match_strength": {"type": "number"}},
            "required": ["exposure_ev", "contrast", "highlights", "shadows", "saturation",
                         "temperature", "tint", "clarity", "vignette", "style_match_strength"]},
        "creative_generate": {"type": "boolean"},
    },
    "required": ["mode", "diagnosis", "subject_bbox", "face_bbox", "corrections", "tone", "creative_generate"],
}

CONSISTENCY_SCHEMA = {
    "type": "object",
    "properties": {
        "exposure_ev": {"type": "number"}, "temperature": {"type": "number"},
        "tint": {"type": "number"}, "contrast": {"type": "number"},
        "saturation": {"type": "number"}, "consistency": {"type": "number"},
        "comment": {"type": "string"},
    },
    "required": ["exposure_ev", "temperature", "tint", "contrast", "saturation", "consistency", "comment"],
}

CONSISTENCY_DELTA_CLAMP = {"exposure_ev": 0.5, "temperature": 0.4, "tint": 0.4,
                          "contrast": 0.3, "saturation": 0.3}


class GeminiClient:
    def __init__(self, settings: Settings):
        if not settings.api_key:
            raise RuntimeError("No Gemini API key set. Add one in Settings, or use Dry run.")
        from google import genai
        self._settings = settings
        self._client = genai.Client(api_key=settings.api_key)

    # -- recipe (prompt only) --
    def analyze(self, preview: Image.Image, mode: Mode, user_prompt: str) -> Recipe:
        return self._recipe_call([preview, build_recipe_prompt(mode, user_prompt, has_reference=False)], mode)

    # -- recipe (example + prompt = combo / example-only) --
    def analyze_with_reference(self, target_preview: Image.Image, reference_preview: Image.Image,
                               mode: Mode, user_prompt: str) -> Recipe:
        prompt = build_recipe_prompt(mode, user_prompt, has_reference=True)
        return self._recipe_call([reference_preview, target_preview, prompt], mode)

    def _recipe_call(self, contents, mode: Mode) -> Recipe:
        from google.genai import types
        response = self._client.models.generate_content(
            model=self._settings.model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=RECIPE_SCHEMA),
        )
        try:
            payload = json.loads(response.text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise RuntimeError(f"Gemini returned non-JSON: {str(response.text)[:300]}") from exc
        return Recipe.model_validate(payload).bounded_for_mode(mode)

    # -- generative pixel edit (Creative mode, optional) --
    def creative_edit(self, image: Image.Image, prompt: str,
                      reference: Image.Image | None = None) -> Image.Image | None:
        from google.genai import types
        instruction = ("Edit the target photo into a polished JPG. Keep identity, clothing, scene, "
                       "and composition recognizable. Avoid beauty retouching unless explicitly asked. ")
        if reference is not None:
            contents = [reference, image, instruction +
                        "Use the first image as the visual style/reference and the second as the target "
                        "to edit. User request: " + prompt]
        else:
            contents = [image, instruction + "User request: " + prompt]
        response = self._client.models.generate_content(
            model=self._settings.image_model,
            contents=contents,
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
        for candidate in response.candidates or []:
            if not candidate.content or not candidate.content.parts:
                continue
            for part in candidate.content.parts:
                inline = getattr(part, "inline_data", None)
                if inline and inline.data:
                    return Image.open(BytesIO(inline.data)).convert("RGB")
        return None

    # -- batch consistency critic (hidden sparring) --
    def consistency_deltas(self, reference_preview: Image.Image, candidates_sheet: Image.Image,
                           round_i: int, total: int) -> dict:
        from google.genai import types
        prompt = (
            "You are a photo color/tone expert making a SET of photos look CONSISTENT with each other "
            "and matching the reference look. The first image is the REFERENCE. The second image is the "
            "current candidate SET tiled together. Suggest ONE small GLOBAL correction for the whole set "
            "(not per image). Keep it gentle. Return JSON: exposure_ev (+brighter/-darker), temperature "
            "(+warmer/-cooler), tint (+green/-magenta), contrast, saturation (all roughly -1..1), "
            "consistency (0-100 = how uniform & on-reference it ALREADY is), comment (short). "
            f"This is sparring round {round_i+1}/{total}.")
        try:
            response = self._client.models.generate_content(
                model=self._settings.model,
                contents=[reference_preview, candidates_sheet, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_schema=CONSISTENCY_SCHEMA,
                    temperature=0.2),
            )
            obj = json.loads(response.text)
        except Exception as exc:  # non-fatal: skip this round
            return {"error": str(exc)[:200]}
        for k, lim in CONSISTENCY_DELTA_CLAMP.items():
            try:
                obj[k] = max(-lim, min(lim, float(obj.get(k, 0.0))))
            except (TypeError, ValueError):
                obj[k] = 0.0
        try:
            obj["consistency"] = float(obj.get("consistency", 0))
        except (TypeError, ValueError):
            obj["consistency"] = 0.0
        return obj


def build_recipe_prompt(mode: Mode, user_prompt: str, *, has_reference: bool) -> str:
    mode_instruction = (
        "FAITHFUL mode: prefer subtle, non-generative corrections only. Keep values near neutral "
        "unless an issue is obvious."
        if mode == Mode.faithful else
        "CREATIVE mode: allow stronger correction if it makes the subject look more natural. Set "
        "creative_generate true only when local correction is unlikely to be enough.")
    reference_instruction = (
        "The first image is the reference look; the second is the target. Estimate tone/style so the "
        "target resembles the reference while staying photographic. style_match_strength controls how "
        "strongly the local editor transfers the reference look."
        if has_reference else
        "No reference image is provided. Use the user prompt to choose tone and geometry.")
    return f"""
You are advising a RAW/JPG photo editor.

Goal: return a complete local editing recipe (geometry/proportion, tone/color, crop, optional creative).

Rules:
- Do not request beauty retouching. Do not change identity, body type, clothing, product design, or scene.
- Estimate normalized bounding boxes in the displayed image.
- A too-wide/flattened subject -> subject_width_scale below 1.0; too-narrow -> above 1.0.
- crop_ratio "original" unless the user asks for a ratio.
- confidence below 0.45 if no clear subject to correct.
- saturation is a multiplier (1.0 unchanged). temperature: - cooler / + warmer. tint: - greener / + magenta.
- Return JSON only per the provided schema.

{reference_instruction}

{mode_instruction}

User request:
{user_prompt or "Produce a realistic, well-balanced edit."}
""".strip()
