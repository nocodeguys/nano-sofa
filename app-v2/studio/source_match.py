"""Seria (in-place recolor) output geometry: the recolor of a photo must come
back at that photo's own aspect and pixel size, not at the page's aspect /
resolution pickers. Those pickers describe a NEW photograph; a recolor is the
same photograph. When the two disagreed, the model was told "keep slot 1's
aspect ratio" while ImageConfig forced another one, so it outpainted the
frame (slightly wider crop) and returned it at the picker's tier (2K over a
1K source → a bigger file of the same picture).

match_source_output picks the request aspect/resolution from the source;
fit_to_source snaps the finished master PNG to the source's exact size."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, PngImagePlugin

from app.core.schema_loader import schema
from studio.openai_images import OPENAI_MODELS
from studio.openrouter import OPENROUTER_MODELS
from studio.paths import logger

# Every ratio Gemini's ImageConfig accepts on the image models we ship (the
# schema enum is only the subset offered as a picker on the page).
_GEMINI_ASPECTS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]

# Approximate pixel budget of each tier (1K ≈ 1024², 2K ≈ 2048², 4K ≈ 4096²).
_TIER_PIXELS = {"1K": 1024 * 1024, "2K": 2048 * 2048, "4K": 4096 * 4096}

# Below this much of the source's width the output is left smaller rather
# than upscaled — a model capped under the source's size can't add detail.
_MAX_UPSCALE = 1.15


def _nearest_aspect(width: int, height: int, allowed: list[str]) -> str:
    target = math.log(width / height)

    def distance(aspect: str) -> float:
        w, h = (float(x) for x in aspect.split(":"))
        return abs(math.log(w / h) - target)

    return min(allowed, key=distance)


def _model_aspects_and_tiers(model: str) -> tuple[list[str], list[str]]:
    cfg = OPENROUTER_MODELS.get(model) or OPENAI_MODELS.get(model)
    if cfg is not None:
        return list(cfg.get("aspects") or _GEMINI_ASPECTS), list(cfg.get("resolutions") or [])
    return list(_GEMINI_ASPECTS), schema.resolution_choices_for_model(model)


def match_source_output(
    model: str, source_path: Path, aspect: str, res: str
) -> tuple[str, str, tuple[int, int] | None]:
    """(aspect, res, source size) for recolouring `source_path` on `model`.
    Falls back to the given aspect/res when the source can't be read; a model
    without a resolution choice keeps `res` (its provider default decides)."""
    try:
        with Image.open(source_path) as im:
            width, height = im.size
    except Exception as exc:
        logger.warning("Recolor source unreadable for size match (%s): %s", source_path, exc)
        return aspect, res, None

    aspects, tiers = _model_aspects_and_tiers(model)
    matched_aspect = _nearest_aspect(width, height, aspects)
    matched_res = res
    if tiers:
        need = width * height * 0.9
        matched_res = next((t for t in tiers if _TIER_PIXELS.get(t, 0) >= need), tiers[-1])
    if (matched_aspect, matched_res) != (aspect, (res or "").split(" ")[0]):
        logger.info(
            "Recolor follows source %dx%d: aspect %s→%s, res %s→%s",
            width, height, aspect, matched_aspect, res, matched_res,
        )
    return matched_aspect, matched_res, (width, height)


def fit_to_source(output_path: Path, size: tuple[int, int] | None) -> None:
    """Centre-crop the master PNG to the source's exact ratio, then resize it
    to the source's pixel size (never upscaling past _MAX_UPSCALE). Keeps the
    nano_sofa_* tEXt identity chunks. Never raises — a failed snap leaves the
    render as the model returned it."""
    if size is None:
        return
    src_w, src_h = size
    try:
        with Image.open(output_path) as im:
            im.load()
            text = dict(getattr(im, "text", None) or {})
            out = im.copy()
        if out.size == (src_w, src_h):
            return

        w, h = out.size
        target_ratio = src_w / src_h
        if abs(math.log((w / h) / target_ratio)) > 0.002:
            if w / h > target_ratio:
                new_w = round(h * target_ratio)
                left = (w - new_w) // 2
                out = out.crop((left, 0, left + new_w, h))
            else:
                new_h = round(w / target_ratio)
                top = (h - new_h) // 2
                out = out.crop((0, top, w, top + new_h))

        if out.width * _MAX_UPSCALE >= src_w:
            out = out.resize((src_w, src_h), Image.LANCZOS)

        info = PngImagePlugin.PngInfo()
        for k, v in text.items():
            info.add_text(k, v)
        out.save(output_path, format="PNG", pnginfo=info)
        logger.info("Recolor snapped %dx%d → %dx%d (source %dx%d)", w, h, *out.size, src_w, src_h)
    except Exception as exc:
        logger.warning("Recolor size snap skipped: %s", exc)
