"""
pipeline.py — orchestration for EditMyRaw.

Workflows: 'prompt' | 'example' | 'combo'. Modes: faithful | creative.
Per image: build a recipe (Gemini or neutral) -> apply geometry + reference look
+ tone, or (creative) a generative edit. Memory-bounded: each full-res result is
saved immediately and dropped; only small previews are kept. An optional hidden
batch-consistency sparring loop nudges the whole set to a uniform look. Exports
JPEG/TIFF + ZIP.
"""

from __future__ import annotations

import gc
import glob
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import raw_io
from .config import Settings, load_settings
from .geometry import apply_geometry
from .recipe import Mode, Recipe, ToneAdjustments, neutral_recipe
from .style import apply_look_profile, build_look_profile
from .tone import apply_tone

WORK_PREVIEW_PX = 768      # per-image preview kept in memory for consistency
THUMB_PX = 320             # before/after thumbnails for the GUI
CONSISTENCY_SAMPLE = 12    # how many images the critic actually looks at


def _noop(*_a, **_k):
    pass


def expand_inputs(items) -> list:
    files = []
    for item in items:
        item = os.path.expanduser(str(item))
        if os.path.isdir(item):
            for name in sorted(os.listdir(item)):
                p = os.path.join(item, name)
                if os.path.isfile(p) and raw_io.is_supported(p):
                    files.append(p)
        elif any(ch in item for ch in "*?["):
            files.extend(sorted(p for p in glob.glob(item) if raw_io.is_supported(p)))
        elif os.path.isfile(item) and raw_io.is_supported(item):
            files.append(item)
    seen, out = set(), []
    for f in files:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def _unique_stem(stem: str, used: set) -> str:
    base, name, k = stem, stem, 2
    while name in used:
        name = f"{base}-{k}"
        k += 1
    used.add(name)
    return name


def _sample(seq, k):
    if len(seq) <= k:
        return list(seq)
    step = len(seq) / k
    return [seq[int(i * step)] for i in range(k)]


@dataclass
class ImageOutcome:
    stem: str
    source: str
    recipe: Recipe
    generated: bool
    before: Image.Image
    after: Image.Image
    out_path: str = ""
    work: Image.Image = None  # small preview used by the consistency critic


def _build_recipe(client, preview, ref_preview, workflow, mode, prompt, dry_run):
    if dry_run or client is None:
        return neutral_recipe(mode, prompt)
    if workflow == "combo" and ref_preview is not None:
        return client.analyze_with_reference(preview, ref_preview, mode, prompt)
    if workflow == "prompt":
        return client.analyze(preview, mode, prompt)
    return neutral_recipe(mode, prompt)  # example: look transfer is local


def _edit_one(image, settings, client, mode, workflow, prompt, reference_image,
              ref_preview, look_profile, skin_mode, dry_run, allow_generative):
    preview = raw_io.make_preview(image, settings.max_preview_px)
    recipe = _build_recipe(client, preview, ref_preview, workflow, mode, prompt, dry_run)
    output, generated = None, False
    if mode == Mode.creative and allow_generative and recipe.creative_generate and client is not None:
        output = client.creative_edit(image, prompt, reference=reference_image)
        generated = output is not None
    if output is None:
        output = apply_geometry(image, recipe)
        if look_profile is not None:
            output = apply_look_profile(output, look_profile,
                                        strength=recipe.tone.style_match_strength, skin_mode=skin_mode)
        output = apply_tone(output, recipe.tone)
    return output, recipe, generated


def run(inputs, out_dir="exports", *, workflow="prompt", mode="faithful", prompt="",
        reference=None, skin_mode="face", fmt="jpg", quality=95, dry_run=False,
        allow_generative=False, batch_consistency=True, consistency_rounds=2,
        settings: Settings | None = None, progress=None, make_zip=True,
        consistency_target=92.0) -> dict:
    progress = progress or _noop
    settings = settings or load_settings()
    mode_enum = Mode(mode)
    inputs = expand_inputs(inputs)
    if not inputs:
        raise ValueError("No supported input images.")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    ext = ".tiff" if fmt == "tiff" else ".jpg"

    client = None
    if not dry_run and settings.api_key:
        from .gemini import GeminiClient
        client = GeminiClient(settings)

    # Reference look (example/combo)
    reference_image = ref_preview = look_profile = None
    if reference and str(reference).lower() != "none" and os.path.exists(str(reference)):
        progress(0.04, "Reading reference…")
        reference_image = raw_io.load_image(reference)
        ref_preview = raw_io.make_preview(reference_image, settings.max_preview_px)
        look_profile = build_look_profile(reference_image, skin_mode=skin_mode)

    # --- Pass 1: edit + save each image, keep only small previews (bounded memory) ---
    n = len(inputs)
    used: set = set()
    outcomes: list[ImageOutcome] = []
    for i, src in enumerate(inputs):
        progress(0.06 + 0.66 * i / n, f"Editing {i+1}/{n}: {os.path.basename(src)}")
        image = raw_io.load_image(src)
        out_img, recipe, generated = _edit_one(
            image, settings, client, mode_enum, workflow, prompt, reference_image,
            ref_preview, look_profile, skin_mode, dry_run, allow_generative)
        stem = _unique_stem(Path(src).stem, used)
        out_path = os.path.join(out_dir, f"{stem}_edit{ext}")
        raw_io.save_image(out_img, out_path, fmt=fmt, quality=quality)  # provisional = final if no global tone
        outcomes.append(ImageOutcome(
            stem=stem, source=src, recipe=recipe, generated=generated,
            before=raw_io.make_preview(image, THUMB_PX),
            after=raw_io.make_preview(out_img, THUMB_PX),
            out_path=out_path,
            work=raw_io.make_preview(out_img, WORK_PREVIEW_PX)))
        del out_img, image
    gc.collect()

    # --- Hidden batch-consistency sparring (one global tone nudge for the whole set) ---
    gemini_log: list = []
    global_tone = ToneAdjustments()
    if batch_consistency and client is not None and n >= 2:
        global_tone, gemini_log = _spar_for_consistency(
            client, outcomes, ref_preview, consistency_rounds, consistency_target, progress)

    # --- Pass 2: only if a global tone was decided, reload + re-apply + re-save ---
    if _nonzero_tone(global_tone):
        progress(0.9, "Applying consistency pass…")
        for i, oc in enumerate(outcomes):
            img = raw_io.load_image(oc.out_path)
            final = apply_tone(img, global_tone)
            raw_io.save_image(final, oc.out_path, fmt=fmt, quality=quality)
            oc.after = raw_io.make_preview(final, THUMB_PX)
            del img, final
        gc.collect()

    out_paths = [oc.out_path for oc in outcomes]

    zip_path = None
    if make_zip and len(out_paths) > 1:
        progress(0.95, "Zipping…")
        zip_path = os.path.join(out_dir, "edits.zip")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as z:
            for p in out_paths:
                z.write(p, os.path.basename(p))

    progress(1.0, f"Done — {n} image(s) in {out_dir}")
    return {
        "count": n, "out_dir": out_dir, "out_paths": out_paths, "zip_path": zip_path,
        "gemini_log": gemini_log, "global_tone": global_tone.model_dump(),
        "outcomes": outcomes, "key_source": settings.key_source,
    }


def _nonzero_tone(t: ToneAdjustments) -> bool:
    return (abs(t.exposure_ev) > 1e-3 or abs(t.temperature) > 1e-3 or abs(t.tint) > 1e-3
            or abs(t.contrast) > 1e-3 or abs(t.saturation - 1.0) > 1e-3)


def _spar_for_consistency(client, outcomes, ref_preview, rounds, target, progress):
    from .sheet import tile_previews
    log = []
    delta = {"exposure_ev": 0.0, "temperature": 0.0, "tint": 0.0, "contrast": 0.0, "saturation": 0.0}
    sample = _sample(outcomes, CONSISTENCY_SAMPLE)
    ref_img = ref_preview if ref_preview is not None else sample[len(sample) // 2].work
    for r in range(rounds):
        progress(0.74 + 0.14 * r / max(1, rounds), f"AI consistency: round {r+1}/{rounds}…")
        tone_now = _delta_to_tone(delta)
        previews = [apply_tone(oc.work, tone_now) if _nonzero_tone(tone_now) else oc.work for oc in sample]
        sheet = tile_previews(previews)
        res = client.consistency_deltas(ref_img, sheet, r, rounds)
        if not res or "error" in res:
            log.append(f"round {r+1}: skipped ({res.get('error','?') if res else '?'})")
            break
        damp = 0.75 ** r
        for k in delta:
            delta[k] += float(res.get(k, 0.0)) * damp
        score = res.get("consistency", 0.0)
        log.append(f"round {r+1}: consistency {score:.0f}/100 — {res.get('comment','')[:80]}")
        progress(0.74 + 0.14 * (r + 1) / max(1, rounds), f"AI consistency {r+1}/{rounds} — {score:.0f}/100")
        if score >= target:
            break
    return _delta_to_tone(delta), log


def _delta_to_tone(delta: dict) -> ToneAdjustments:
    return ToneAdjustments(
        exposure_ev=float(max(-1.5, min(1.5, delta["exposure_ev"]))),
        temperature=float(max(-1.0, min(1.0, delta["temperature"]))),
        tint=float(max(-1.0, min(1.0, delta["tint"]))),
        contrast=float(max(-0.8, min(0.8, delta["contrast"]))),
        saturation=float(max(0.2, min(1.8, 1.0 + delta["saturation"]))),
    )
