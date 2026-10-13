"""Meli — wood-colour recolor for solid-wood beds (Lab tab, /meli).

A deliberately narrow edit: the uploaded photo of a wooden bed comes back
with ONLY the colour / finish of the bed's wood changed — no upholstery, no
scene, no camera. Runs on every OpenRouter image model with the user's
OpenRouter key (same key model as /editorial and /lab).

The palette lives in ``app-v2/meli/palette.json`` and the finish photographs
in ``app-v2/meli/references/`` (``<id>.jpg``, ``<id>-2.jpg`` …). Both are read
per request, so adding a colour is a file edit, never a code change or a
restart. A palette entry::

    {"id": "dab-naturalny", "name_pl": "Dąb naturalny", "hex": "#C8A27A",
     "finish": "stain", "prompt_en": "natural light oak with honey undertone"}

``finish`` is "stain" (transparent stain / oil — the grain stays fully
visible) or "opaque" (covering paint / lacquer). ``hex`` and ``prompt_en``
are optional; the reference photographs are the strongest colour authority.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image

from studio.errors import _validation_error
from studio.external_engine import ALL_ASPECTS, ExternalEngineError
from studio.media import _derived_url, _parse_quality, _prune_storage, _save_upload
from studio.openrouter import OPENROUTER_MODELS, generate_openrouter
from studio.paths import _THIS, logger

router = APIRouter()

_MELI_DIR = _THIS / "meli"
_PALETTE_PATH = _MELI_DIR / "palette.json"
_REFS_DIR = _MELI_DIR / "references"
_REF_EXTS = (".jpg", ".jpeg", ".png", ".webp")
_FINISHES = ("stain", "opaque")
_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
_DEFAULT_MODEL = "google/gemini-nano-banana-2.1"
# Base photo + finish photos + colour patch. A model with a smaller cap keeps
# the base photo and drops the finish photos from the end.
_MAX_FINISH_REFS = 4
_SEND_MAX_EDGE = 2048


def _load_palette() -> list[dict]:
    try:
        raw = json.loads(_PALETTE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        logger.warning("Meli palette unreadable (%s): %s", _PALETTE_PATH, exc)
        return []
    colors = raw.get("colors", []) if isinstance(raw, dict) else raw
    palette = []
    for entry in colors if isinstance(colors, list) else []:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        hex_match = _HEX_RE.match(str(entry.get("hex") or ""))
        palette.append({
            "id": str(entry["id"]),
            "name_pl": str(entry.get("name_pl") or entry["id"]),
            "hex": f"#{hex_match.group(1).upper()}" if hex_match else "",
            "finish": entry.get("finish") if entry.get("finish") in _FINISHES else "stain",
            "prompt_en": str(entry.get("prompt_en") or ""),
            "group": str(entry.get("group") or ""),
        })
    return palette


def _reference_files(color_id: str) -> list[Path]:
    """`<id>.jpg`, then `<id>-2.jpg`, `<id>-3.jpg` … in natural order."""
    if not _REFS_DIR.is_dir() or not color_id:
        return []
    found = []
    for path in _REFS_DIR.iterdir():
        if path.suffix.lower() not in _REF_EXTS:
            continue
        stem = path.stem
        if stem == color_id:
            found.append((0, path))
        elif stem.startswith(color_id + "-") and stem[len(color_id) + 1:].isdigit():
            found.append((int(stem[len(color_id) + 1:]), path))
    return [path for _n, path in sorted(found)]


def _model_entry(slug: str, cfg: dict) -> dict:
    return {
        "id": slug,
        "label": cfg["label"],
        "max_refs": cfg["max_refs"],
        "price_hint": cfg.get("price_hint", ""),
        "aspects": list(cfg.get("aspects") or ALL_ASPECTS),
        "resolutions": list(cfg.get("resolutions") or ["auto"]),
        "qualities": list(cfg.get("qualities") or []),
        "default_quality": cfg.get("default_quality", ""),
    }


@router.get("/api/meli/config")
def meli_config():
    palette = [
        {**color, "references": [f"/api/meli/ref/{p.name}" for p in _reference_files(color["id"])]}
        for color in _load_palette()
    ]
    models = [_model_entry(slug, cfg) for slug, cfg in OPENROUTER_MODELS.items()]
    return {
        "palette": palette,
        "models": models,
        "default_model": _DEFAULT_MODEL if _DEFAULT_MODEL in OPENROUTER_MODELS
        else (models[0]["id"] if models else None),
    }


@router.get("/api/meli/ref/{name}")
def meli_reference(name: str):
    path = (_REFS_DIR / name).resolve()
    if path.parent != _REFS_DIR.resolve() or path.suffix.lower() not in _REF_EXTS or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


def nearest_aspect(width: int, height: int, allowed: list[str]) -> str:
    """The allowed aspect closest to the photo's own ratio (log distance), so
    the edit is not recomposed into a different frame."""
    import math

    target = math.log(width / height)

    def distance(aspect: str) -> float:
        w, h = (float(x) for x in aspect.split(":"))
        return abs(math.log(w / h) - target)

    return min(allowed or ALL_ASPECTS, key=distance)


def _send_copy(path: Path, suffix: str) -> Path:
    """JPEG copy (≤ 2048 px, q95) of an uploaded PNG — keeps the request body
    small without visibly touching the photo the model must preserve."""
    image = Image.open(path).convert("RGB")
    image.thumbnail((_SEND_MAX_EDGE, _SEND_MAX_EDGE), Image.LANCZOS)
    out = path.with_name(path.stem + suffix + ".jpg")
    image.save(out, format="JPEG", quality=95)
    return out


def build_meli_prompt(*, name: str, description: str, hex_value: str, finish: str,
                      finish_slots: list[int], patch_slot: Optional[int]) -> str:
    target = name
    if description:
        target += f" — {description}"
    if hex_value:
        target += f" (target colour {hex_value})"
    if finish == "opaque":
        finish_clause = (
            "Apply it as an opaque satin paint / lacquer: a solid, even colour on "
            "every wooden part. The wood grain may show only as a faint surface "
            "texture through the paint; no original wood tone shows through."
        )
    else:
        finish_clause = (
            "Apply it as a transparent wood stain / oil: the natural grain, knots, "
            "growth rings and pores from image 1 stay fully visible, in exactly "
            "the same places and with the same pattern — only the tone of the "
            "wood changes. Natural tonal variation between boards and along the "
            "grain is kept, shifted into the new colour. Keep the original sheen "
            "level of the finish."
        )
    lines = [
        "Edit image 1. This is an in-place colour edit of a photograph of a "
        "solid-wood bed, not a new picture.",
        f"\nCHANGE ONLY THIS: the colour and finish of the bed's visible wooden "
        f"parts — frame, headboard, footboard, side rails, slats and legs where "
        f"visible. New wood colour: {target}. {finish_clause}",
        "\nKEEP EVERYTHING ELSE IDENTICAL TO IMAGE 1 — HARD REQUIREMENT: the same "
        "framing, crop, camera angle, perspective and lens; the same lighting, "
        "light direction, shadows, reflections and white balance; the same "
        "background, walls, floor, rug, windows and all props and decorations; "
        "the same mattress, bedding, pillows, throws and any upholstered or "
        "fabric parts of the bed with their original colour; the same metal "
        "hardware. The bed keeps its exact geometry, proportions, joints, "
        "edges, profiles, screws and the exact wood-grain pattern. Other wooden "
        "objects in the room (floor, nightstands, shelves) keep their original "
        "colour unless they are part of the bed. Do not add, remove, move, "
        "restyle, retouch or re-light anything. Output the same scene at the "
        "same composition, with only the bed's wood recoloured.",
        "\nThe new colour must look physically real on wood under the scene's "
        "existing light: highlights and shadows on the wood follow image 1, "
        "never a flat digital overlay, never a colour cast spilling onto the "
        "bedding, wall or floor.",
    ]
    if finish_slots:
        label = ", ".join(str(n) for n in finish_slots)
        noun = "Images" if len(finish_slots) > 1 else "Image"
        lines.append(
            f"\nWOOD FINISH AUTHORITY ({noun.lower()} {label}): {noun} {label} "
            f"{'are photographs' if len(finish_slots) > 1 else 'is a photograph'} of "
            f"the real target finish {name}. Copy ONLY the wood's colour, tone "
            f"variation, grain visibility and sheen from {'them' if len(finish_slots) > 1 else 'it'}. "
            f"Ignore their object, shape, crop, scale, lighting and background. "
            f"The grain pattern itself always comes from image 1."
        )
    if patch_slot is not None:
        lines.append(
            f"\nCOLOUR AUTHORITY (image {patch_slot}): image {patch_slot} is a flat "
            f"patch of the target colour {hex_value}. Under the scene's light the "
            f"mid-tones of the wood match it; copy nothing else from it."
        )
    return "\n".join(lines)


@router.post("/api/meli/recolor")
async def meli_recolor(
    openrouter_key: str = Form(""),
    model: str = Form(_DEFAULT_MODEL),
    color: str = Form(""),
    custom_name: str = Form(""),
    custom_hex: str = Form(""),
    custom_finish: str = Form("stain"),
    product_name: str = Form(""),
    res: str = Form("2K"),
    quality: str = Form(""),
    output_format: str = Form("jpg"),
    output_quality: str = Form("90"),
    base: Optional[UploadFile] = File(None),
    references: list[UploadFile] = File(default_factory=list),
):
    if not openrouter_key.strip():
        return _validation_error("Wklej klucz OpenRouter (sk-or-…).", "MISSING_OPENROUTER_KEY")
    cfg = OPENROUTER_MODELS.get(model)
    if cfg is None:
        return _validation_error("Nieznany model OpenRouter.", "UNKNOWN_MODEL")
    if base is None:
        return _validation_error("Wgraj zdjęcie łóżka.", "MISSING_BASE_IMAGE")

    if color:
        entry = next((c for c in _load_palette() if c["id"] == color), None)
        if entry is None:
            return _validation_error("Nieznany kolor z palety Meli.", "UNKNOWN_COLOR")
        name, description = entry["name_pl"], entry["prompt_en"]
        hex_value, finish = entry["hex"], entry["finish"]
        finish_paths = _reference_files(entry["id"])
    else:
        name = " ".join(custom_name.split())[:120]
        hex_match = _HEX_RE.match(custom_hex.strip())
        hex_value = f"#{hex_match.group(1).upper()}" if hex_match else ""
        if not name and not hex_value:
            return _validation_error("Wybierz kolor z palety albo opisz własny.", "MISSING_COLOR")
        name = name or hex_value
        description = ""
        finish = custom_finish if custom_finish in _FINISHES else "stain"
        finish_paths = []

    try:
        base_path = await _save_upload(base, suffix="_meli")
    except Exception:
        return _validation_error("Nie udało się odczytać zdjęcia łóżka.", "BAD_INPUT_IMAGE")
    for idx, ref in enumerate(references or []):
        try:
            finish_paths.append(await _save_upload(ref, suffix=f"_meliref{idx}"))
        except Exception as exc:
            logger.warning("Meli reference #%d unreadable, ignoring: %s", idx, exc)

    base_image = Image.open(base_path)
    width, height = base_image.size
    send_base = await asyncio.to_thread(_send_copy, base_path, "_send")
    aspect = nearest_aspect(width, height, list(cfg.get("aspects") or ALL_ASPECTS))

    # Reference plan within the model's cap: base first, then finish photos,
    # then the colour patch (only with a known hex and room left).
    cap = max(1, int(cfg["max_refs"]))
    plan = [("base_product", send_base, Image.open(send_base))]
    room = cap - 1
    use_patch = bool(hex_value) and room >= 1
    finish_room = min(_MAX_FINISH_REFS, room - (1 if use_patch else 0))
    if finish_room < 1 and finish_paths and room >= 1:
        # Prefer the real finish photograph over the flat patch.
        use_patch, finish_room = False, 1
    for path in finish_paths[:max(0, finish_room)]:
        plan.append(("wood_finish", path, Image.open(path)))
    finish_slots = list(range(2, len(plan) + 1))
    patch_slot = None
    if use_patch and len(plan) < cap:
        rgb = tuple(int(hex_value[i:i + 2], 16) for i in (1, 3, 5))
        plan.append(("color_patch", None, Image.new("RGB", (256, 256), rgb)))
        patch_slot = len(plan)

    prompt = build_meli_prompt(
        name=name, description=description, hex_value=hex_value, finish=finish,
        finish_slots=finish_slots, patch_slot=patch_slot,
    )
    product = " ".join(product_name.split())[:80]
    png_meta = {
        "nano_sofa_mode": "meli",
        "nano_sofa_wood_color": name,
        "nano_sofa_wood_color_id": color or "custom",
        "nano_sofa_wood_finish": finish,
        "nano_sofa_color_hex": hex_value,
        "nano_sofa_product": product,
    }
    logger.info("Meli recolor: model=%s colour=%s finish=%s refs=%d aspect=%s",
                model, color or "custom", finish, len(plan), aspect)
    try:
        out = await asyncio.to_thread(
            generate_openrouter,
            api_key=openrouter_key.strip(), model=model, prompt=prompt, aspect=aspect,
            references=plan, quality=quality, resolution=res, png_meta=png_meta,
            prompt_summary=f"Meli · {product or 'łóżko'} · {name}",
        )
    except ExternalEngineError as exc:
        return JSONResponse(
            {"error": exc.message_pl, "error_code": exc.code, "error_detail": exc.detail,
             "retryable": exc.retryable},
            status_code=exc.http_status,
        )

    image_url, fmt_used, _downgraded = await _derived_url(
        out["output_path"], output_format, _parse_quality(output_quality), False,
    )
    await asyncio.to_thread(_prune_storage)
    return {
        "success": True,
        "generation_id": out["generation_id"],
        "image_url": image_url,
        "format": fmt_used,
        "cost": out["cost"],
        "model": out["model_id"],
        "resolution": out.get("resolution") or "auto",
        "quality": out.get("quality") or "",
        "aspect": aspect,
        "elapsed_ms": out["elapsed_ms"],
        "color": name,
        "color_id": color or "custom",
        "finish": finish,
        "references_sent": len(plan),
    }
