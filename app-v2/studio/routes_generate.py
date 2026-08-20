"""Render endpoints: single generate, colour-variant set, Fotosesja grid,
per-tile regenerate. Everything funnels through _build_generation_request."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import replace as dataclass_replace
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.generator import generate
from studio.errors import _item_error, _result_error, _validation_error
from studio.mappings import _compose_bedding_description
from studio.media import (
    _TRANSPARENT_ENVS,
    _derived_url,
    _parse_quality,
    _prune_storage,
    _resolve_anchor_path,
    _save_upload,
)
from studio.openrouter import OPENROUTER_MODELS, OpenRouterError, generate_openrouter
from studio.paths import logger
from studio.request_builder import (
    _build_freeform_request,
    _build_generation_request,
    _recolor_request,
)

router = APIRouter()

# Cap simultaneous Gemini calls within a single batch (variant set / photoshoot)
# so we never fire 8+ requests at one API key at once → self-induced 429/503.
# The anchor renders first (sequentially), then variants fan out through this
# gate. Created lazily so it binds to the running event loop; per-process.
_BATCH_CONCURRENCY = int(os.environ.get("BATCH_CONCURRENCY", "3"))
_gen_semaphore: Optional[asyncio.Semaphore] = None


def _batch_semaphore() -> asyncio.Semaphore:
    global _gen_semaphore
    if _gen_semaphore is None:
        _gen_semaphore = asyncio.Semaphore(_BATCH_CONCURRENCY)
    return _gen_semaphore


async def _capped(fn, *args):
    """Run blocking render `fn(*args)` in a thread, max _BATCH_CONCURRENCY at once."""
    async with _batch_semaphore():
        return await asyncio.to_thread(fn, *args)


@router.post("/api/generate")
async def api_generate(
    api_key: str = Form(""),
    kind: str = Form("sofa"),
    color: str = Form("greige"),
    color_custom: str = Form(""),
    mat: str = Form("boucle"),
    mat_notes: str = Form(""),
    size: str = Form("3"),
    legs: str = Form("keep"),
    cam: str = Form("studio"),
    lens: str = Form("50mm_natural"),
    tod: str = Form("noon_neutral"),
    shadow: str = Form("soft_diffuse"),
    # New structured camera fields — see _build_generation_request for the
    # mapping tables. Empty values fall back to the `cam` preset.
    shot: str = Form(""),
    yaw: str = Form(""),
    height: str = Form(""),
    dof: str = Form(""),
    detail_region: str = Form(""),
    env: str = Form(""),
    env_note: str = Form(""),
    env_mode: str = Form(""),
    model: str = Form("gemini-2.5-flash-image"),
    aspect: str = Form("4:3"),
    res: str = Form("1K"),
    seed: str = Form(""),
    output_format: str = Form("jpg"),
    output_quality: str = Form("82"),
    base_image: Optional[UploadFile] = File(None),
    scene_image: Optional[UploadFile] = File(None),
    references: list[UploadFile] = File(default_factory=list),
    refs_lock: str = Form(""),
    preserve_base: str = Form(""),
    bedding: str = Form(""),
    bedding_custom: str = Form(""),
    throw: str = Form(""),
    tidy: str = Form(""),
    density: str = Form(""),
    accents: str = Form(""),
    bed_note: str = Form(""),
):
    if not api_key.strip():
        return _validation_error("Brak klucza API.", "MISSING_API_KEY")
    if base_image is None:
        return _validation_error("Brak zdjęcia bazowego.", "MISSING_BASE_IMAGE")

    try:
        upload_path = await _save_upload(base_image)
    except Exception as exc:
        return _validation_error(f"Nie udało się odczytać obrazu: {exc}", "BAD_INPUT_IMAGE")

    scene_upload_path: Optional[Path] = None
    if scene_image is not None:
        try:
            scene_upload_path = await _save_upload(scene_image, suffix="_scene")
        except Exception as exc:
            logger.warning("Scene reference image unreadable, ignoring: %s", exc)

    # Optional moodboard references from section 09 "Referencje". Each one that
    # can't be decoded is skipped with a warning rather than failing the whole
    # request — a malformed jpg in slot 3 shouldn't block the render.
    extra_ref_paths: list[Path] = []
    for idx, ref in enumerate(references or []):
        if ref is None:
            continue
        try:
            extra_ref_paths.append(await _save_upload(ref, suffix=f"_ref{idx}"))
        except Exception as exc:
            logger.warning("Reference #%d unreadable, ignoring: %s", idx, exc)

    bedding_desc = ""
    if kind == "bed":
        bedding_desc = _compose_bedding_description(
            bedding=bedding,
            bedding_custom=bedding_custom,
            throw=throw,
            tidy=tidy,
            density=density,
            accents_csv=accents,
            bed_note=bed_note,
        )

    req = _build_generation_request(
        api_key=api_key, kind=kind,
        color=color, color_custom=color_custom,
        mat=mat, mat_notes=mat_notes,
        size=size, legs=legs, cam=cam,
        lens=lens, tod=tod, shadow=shadow,
        shot=shot, yaw=yaw, height=height, dof=dof, detail_region=detail_region,
        env=env, env_note=env_note, env_mode=env_mode,
        model=model, aspect=aspect, res=res, seed=seed,
        base_image_path=upload_path,
        scene_image_path=scene_upload_path,
        extra_reference_paths=extra_ref_paths,
        lock_to_reference=refs_lock.strip().lower() in ("1", "true", "on", "yes"),
        preserve_camera_from_base=preserve_base.strip().lower() in ("1", "true", "on", "yes"),
        bedding_description=bedding_desc,
    )

    logger.info("Generating: %s / %s / %s", req.upholstery_color, req.upholstery_material, req.camera_angle)
    # Off-load the blocking Gemini call (network I/O + up to ~14s of retry
    # backoff) to a thread so the event loop stays responsive — /healthz, the
    # static assets, and other users' renders no longer freeze behind this one.
    # Matches what /api/generate-set and /api/generate-photoshoot already do.
    result = await asyncio.to_thread(generate, req)

    if not result.success or result.output_path is None:
        return _result_error(result)

    # Derive the user-facing download file (default JPG) off the lossless PNG
    # master, then trim the storage volume. The master is kept for reference reuse.
    image_url, fmt_used, downgraded = await _derived_url(
        result.output_path, output_format, _parse_quality(output_quality),
        env in _TRANSPARENT_ENVS,
    )
    await asyncio.to_thread(_prune_storage)

    return {
        "success": True,
        "generation_id": result.generation_id,
        "image_url": image_url,
        "format": fmt_used,
        "format_downgraded": downgraded,
        "cost": result.actual_cost,
        "model": result.model_id,
        "resolution": result.resolution,
        "elapsed_ms": result.elapsed_ms,
    }


@router.post("/api/generate-set")
async def api_generate_set(
    api_key: str = Form(""),
    kind: str = Form("sofa"),
    colors_csv: str = Form(""),     # comma-separated English color ids (anchor first)
    # Optional materials, paired positionally with colors_csv. Empty → fall
    # back to a single shared `mat` for the whole batch (legacy behavior).
    # When non-empty but shorter than colors_csv, the trailing colors reuse
    # the LAST material in the list. When longer, the excess is ignored.
    materials_csv: str = Form(""),
    color_custom: str = Form(""),
    mat: str = Form("boucle"),
    mat_notes: str = Form(""),
    size: str = Form("3"),
    legs: str = Form("keep"),
    cam: str = Form("studio"),
    lens: str = Form("50mm_natural"),
    tod: str = Form("noon_neutral"),
    shadow: str = Form("soft_diffuse"),
    # Structured camera fields — same semantics as /api/generate. When empty
    # the server falls back to the legacy `cam` preset.
    shot: str = Form(""),
    yaw: str = Form(""),
    height: str = Form(""),
    dof: str = Form(""),
    detail_region: str = Form(""),
    env: str = Form(""),
    env_note: str = Form(""),
    env_mode: str = Form(""),
    # Bed-only styling fields. The bedding description is composed once and
    # reused for every variant — styling shouldn't drift across a color set.
    bedding: str = Form(""),
    bedding_custom: str = Form(""),
    throw: str = Form(""),
    tidy: str = Form(""),
    density: str = Form(""),
    accents: str = Form(""),
    bed_note: str = Form(""),
    model: str = Form("gemini-3.1-flash-image-preview"),
    aspect: str = Form("4:3"),
    res: str = Form("1K"),
    seed: str = Form(""),
    output_format: str = Form("jpg"),
    output_quality: str = Form("82"),
    base_image: Optional[UploadFile] = File(None),
    scene_image: Optional[UploadFile] = File(None),
):
    """
    Generate a color-variant set with consistent scene/background.

    Strategy: render the FIRST color (anchor) normally, then fan out variants
    2..N in parallel using the anchor as BOTH a scene reference image (locks
    the pixel-level background) AND multi-turn history (preserves frame
    identity via Gemini's thought signatures). This combines the two
    documented Gemini mechanisms for identity-preserving edits.

    Returns: {
      anchor:   { color, image_url, cost, ... },
      variants: [{ color, image_url, cost, ... } | { color, error }, ...]
    }
    """
    if not api_key.strip():
        return _validation_error("Brak klucza API.", "MISSING_API_KEY")
    if base_image is None:
        return _validation_error("Brak zdjęcia bazowego.", "MISSING_BASE_IMAGE")

    color_ids = [c.strip() for c in colors_csv.split(",") if c.strip()]
    if len(color_ids) < 2:
        return _validation_error(
            "Wybierz co najmniej 2 kolory dla zestawu wariantów.", "TOO_FEW_COLORS"
        )
    if len(color_ids) > 8:
        return _validation_error(
            "Limit zestawu to 8 kolorów na jeden run.", "TOO_MANY_COLORS"
        )

    try:
        base_path = await _save_upload(base_image)
    except Exception as exc:
        return _validation_error(f"Nie udało się odczytać obrazu: {exc}", "BAD_INPUT_IMAGE")

    # Optional user-supplied scene reference (independent of the auto-anchor flow).
    scene_path: Optional[Path] = None
    if scene_image is not None:
        try:
            scene_path = await _save_upload(scene_image, suffix="_scene")
        except Exception as exc:
            logger.warning("Scene reference image unreadable, ignoring: %s", exc)

    # Materials per variant, paired positionally with color_ids.
    #   - Empty materials_csv → every variant uses the shared `mat`.
    #   - Shorter than colors → last material extends to fill remaining slots.
    #   - Longer than colors → excess is dropped.
    raw_mats = [m.strip() for m in materials_csv.split(",") if m.strip()]
    if not raw_mats:
        material_ids = [mat] * len(color_ids)
    else:
        material_ids = list(raw_mats[:len(color_ids)])
        while len(material_ids) < len(color_ids):
            material_ids.append(raw_mats[-1])

    # Bed styling — compose once, reuse for anchor + every variant. Styling
    # is intentionally locked across the set (the whole point of a variant
    # set is to compare colors/materials on the same staging).
    bedding_desc = ""
    if kind == "bed":
        bedding_desc = _compose_bedding_description(
            bedding=bedding,
            bedding_custom=bedding_custom,
            throw=throw,
            tidy=tidy,
            density=density,
            accents_csv=accents,
            bed_note=bed_note,
        )

    # ------------------------------------------------------------------ #
    # 1. Anchor render — first color in the list.
    # ------------------------------------------------------------------ #
    anchor_color = color_ids[0]
    anchor_mat = material_ids[0]
    logger.info(
        "Variant set: anchor=%s/%s, then %d more (materials=%s)",
        anchor_color, anchor_mat, len(color_ids) - 1, material_ids,
    )

    anchor_req = _build_generation_request(
        api_key=api_key, kind=kind,
        color=anchor_color, color_custom=color_custom,
        mat=anchor_mat, mat_notes=mat_notes,
        size=size, legs=legs, cam=cam,
        lens=lens, tod=tod, shadow=shadow,
        shot=shot, yaw=yaw, height=height, dof=dof, detail_region=detail_region,
        env=env, env_note=env_note, env_mode=env_mode,
        model=model, aspect=aspect, res=res, seed=seed,
        base_image_path=base_path,
        scene_image_path=scene_path,
        bedding_description=bedding_desc,
    )

    anchor_result = await asyncio.to_thread(generate, anchor_req)

    if not anchor_result.success or anchor_result.output_path is None:
        return _result_error(anchor_result)

    transparent_env = env in _TRANSPARENT_ENVS
    qual = _parse_quality(output_quality)
    anchor_url, _afmt, _adn = await _derived_url(
        anchor_result.output_path, output_format, qual, transparent_env
    )
    anchor_payload = {
        "color": anchor_color,
        "material": anchor_mat,
        "image_url": anchor_url,
        "generation_id": anchor_result.generation_id,
        "cost": anchor_result.actual_cost,
        "model": anchor_result.model_id,
        "resolution": anchor_result.resolution,
    }

    # ------------------------------------------------------------------ #
    # 2. Variants 2..N — fan out in parallel. Each one:
    #    - uses the anchor's PNG as scene_reference_image (pixel-lock bg)
    #    - inherits anchor's prior_history (thought-signature identity)
    #    - changes only the upholstery color
    # ------------------------------------------------------------------ #
    anchor_history = anchor_result.next_history

    def _render_variant(color_id: str, material_id: str):
        # Build a request mirroring the anchor, then mutate color + material +
        # scene_reference_image + prior_history.
        v_req = _build_generation_request(
            api_key=api_key, kind=kind,
            color=color_id, color_custom=color_custom,
            mat=material_id, mat_notes=mat_notes,
            size=size, legs=legs, cam=cam,
            lens=lens, tod=tod, shadow=shadow,
            shot=shot, yaw=yaw, height=height, dof=dof, detail_region=detail_region,
            env=env, env_note=env_note, env_mode=env_mode,
            model=model, aspect=aspect, res=res, seed=seed,
            base_image_path=base_path,
            scene_image_path=anchor_result.output_path,  # anchor PNG locks the scene
            bedding_description=bedding_desc,
        )
        v_req = dataclass_replace(
            v_req,
            prior_history=list(anchor_history),
            turn_number=2,
        )
        return generate(v_req)

    variant_pairs = list(zip(color_ids[1:], material_ids[1:]))
    variant_results = await asyncio.gather(
        *(_capped(_render_variant, cid, mid) for cid, mid in variant_pairs),
        return_exceptions=True,
    )

    variants_payload = []
    for (cid, mid), r in zip(variant_pairs, variant_results):
        if isinstance(r, Exception):
            variants_payload.append(_item_error({"color": cid, "material": mid}, r))
            continue
        if not r.success or r.output_path is None:
            variants_payload.append(_item_error({"color": cid, "material": mid}, r))
            continue
        v_url, _vf, _vd = await _derived_url(r.output_path, output_format, qual, transparent_env)
        variants_payload.append({
            "color": cid,
            "material": mid,
            "image_url": v_url,
            "generation_id": r.generation_id,
            "cost": r.actual_cost,
        })

    await asyncio.to_thread(_prune_storage)
    total_cost = anchor_result.actual_cost + sum(
        v.get("cost", 0) for v in variants_payload if "cost" in v
    )

    return {
        "success": True,
        "anchor": anchor_payload,
        "variants": variants_payload,
        "total_cost": total_cost,
        "model": model,
    }


# Fotosesja v2 grid limits (single-user localhost tool; bound cost + fan-out).
_MAX_SOURCES = 8
_MAX_PAIRS = 8
_MAX_GRID_RENDERS = 48


@router.post("/api/generate-variants")
async def api_generate_variants(
    api_key: str = Form(""),
    kind: str = Form("sofa"),
    # Shared colour+material PAIRS applied to EVERY source.
    # JSON: [{"color": "<chip id>", "material": "<chip id>"}, ...]
    pairs_json: str = Form(""),
    color_custom: str = Form(""),
    mat_notes: str = Form(""),
    size: str = Form("3"),
    legs: str = Form("keep"),
    cam: str = Form("studio"),
    lens: str = Form("50mm_natural"),
    tod: str = Form("noon_neutral"),
    shadow: str = Form("soft_diffuse"),
    shot: str = Form(""),
    yaw: str = Form(""),
    height: str = Form(""),
    dof: str = Form(""),
    detail_region: str = Form(""),
    bedding: str = Form(""),
    bedding_custom: str = Form(""),
    throw: str = Form(""),
    tidy: str = Form(""),
    density: str = Form(""),
    accents: str = Form(""),
    bed_note: str = Form(""),
    model: str = Form("gemini-3.1-flash-image-preview"),
    aspect: str = Form("4:3"),
    res: str = Form("1K"),
    seed: str = Form(""),
    output_format: str = Form("jpg"),
    output_quality: str = Form("82"),
    # Sources = base photos. Uploaded files AND/OR refs to existing renders.
    # Each carries a client sid (parallel csv) so results group back per source.
    sources: list[UploadFile] = File(default_factory=list),
    upload_sids_csv: str = Form(""),
    source_refs_csv: str = Form(""),
    ref_sids_csv: str = Form(""),
):
    """
    Fotosesja v2 — apply a shared set of colour+material PAIRS to MANY base photos.

    For every (source × pair) it runs an in-place recolor that keeps the source
    photo's exact angle and background (generator keep_source_scene mode), changing
    only the upholstery colour/material. Sources may be freshly uploaded photos or
    refs to existing renders (generation_id / output basename). Results are grouped
    by source so the UI can show one row per photo.

    Streams NDJSON (application/x-ndjson), one JSON object per line:
      {"type":"meta","total":N,"model":..,"sources":[{sid,source_kind,source_ref,source_url,error?}]}
      {"type":"tile","sid":..,"color":..,"material":..,"image_url"/"generation_id"/"cost" | "error"}  (one per completed render)
      {"type":"done","total_cost":..}
    Pre-flight validation errors are returned as a normal JSON 4xx BEFORE the stream starts.
    """
    if not api_key.strip():
        return _validation_error("Brak klucza API.", "MISSING_API_KEY")

    # ---- parse the shared colour+material pairs ------------------------- #
    try:
        raw_pairs = json.loads(pairs_json) if pairs_json.strip() else []
    except Exception:
        raw_pairs = []
    pairs = []
    for p in raw_pairs if isinstance(raw_pairs, list) else []:
        if not isinstance(p, dict):
            continue
        c = str(p.get("color", "")).strip()
        m = str(p.get("material", "")).strip() or "boucle"
        if c:
            pairs.append({"color": c, "material": m})
    if not pairs:
        return _validation_error("Dodaj co najmniej 1 parę kolor + materiał.", "TOO_FEW_PAIRS")
    if len(pairs) > _MAX_PAIRS:
        return _validation_error(f"Limit par kolor/materiał: {_MAX_PAIRS}.", "TOO_MANY_PAIRS")

    # ---- assemble the ordered source list (uploads, then refs) --------- #
    upload_sids = [s.strip() for s in upload_sids_csv.split(",")]
    ref_items = [r.strip() for r in source_refs_csv.split(",") if r.strip()]
    ref_sids = [s.strip() for s in ref_sids_csv.split(",")]

    resolved: list[dict] = []   # {sid, kind, ref, path|None, url|None, error?}
    for i, up in enumerate(sources or []):
        sid = upload_sids[i] if i < len(upload_sids) and upload_sids[i] else f"u{i}"
        try:
            p = await _save_upload(up, suffix="_src")
            resolved.append({"sid": sid, "kind": "upload", "ref": up.filename or "", "path": p, "url": None})
        except Exception as exc:
            resolved.append({"sid": sid, "kind": "upload", "ref": up.filename or "", "path": None,
                             "url": None, "error": f"Nie udało się odczytać zdjęcia: {exc}"})
    for j, ref in enumerate(ref_items):
        sid = ref_sids[j] if j < len(ref_sids) and ref_sids[j] else f"r{j}"
        path = _resolve_anchor_path(ref)
        if path is None:
            resolved.append({"sid": sid, "kind": "ref", "ref": ref, "path": None, "url": None,
                             "error": "Nie znaleziono zdjęcia (mogło zostać usunięte)."})
        else:
            resolved.append({"sid": sid, "kind": "ref", "ref": ref, "path": path,
                             "url": f"/api/outputs/{path.name}"})

    if not resolved:
        return _validation_error("Wybierz co najmniej 1 zdjęcie bazowe.", "MISSING_SOURCES")
    if len(resolved) > _MAX_SOURCES:
        return _validation_error(f"Limit zdjęć bazowych: {_MAX_SOURCES}.", "TOO_MANY_SOURCES")
    usable = [s for s in resolved if s.get("path")]
    if not usable:
        return _validation_error("Żadnego zdjęcia bazowego nie udało się wczytać.", "BAD_INPUT_IMAGE")
    if len(usable) * len(pairs) > _MAX_GRID_RENDERS:
        return _validation_error(
            f"Za dużo renderów ({len(usable)}×{len(pairs)}). Limit to {_MAX_GRID_RENDERS} na run.",
            "TOO_MANY_RENDERS",
        )

    bedding_desc = ""
    if kind == "bed":
        bedding_desc = _compose_bedding_description(
            bedding=bedding, bedding_custom=bedding_custom, throw=throw,
            tidy=tidy, density=density, accents_csv=accents, bed_note=bed_note,
        )
    qual = _parse_quality(output_quality)
    logger.info("Variant grid: %d sources × %d pairs", len(usable), len(pairs))

    # ---- stream every (source × pair) recolor as NDJSON ---------------- #
    # Pre-flight passed; now emit  meta → one `tile` per completed render → done.
    # The client fills the grid live and drives a real X/N progress bar so the
    # user sees first results immediately instead of waiting for the whole batch.
    def _render(src_path, pair):
        return generate(_recolor_request(
            api_key=api_key, kind=kind,
            color=pair["color"], color_custom=color_custom,
            mat=pair["material"], mat_notes=mat_notes,
            size=size, legs=legs, cam=cam, lens=lens, tod=tod, shadow=shadow,
            shot=shot, yaw=yaw, height=height, dof=dof, detail_region=detail_region,
            model=model, aspect=aspect, res=res, seed=seed,
            bedding_desc=bedding_desc, source_path=src_path,
        ))

    async def _job(s, pair):
        # Never raises — failures become an error tile so the stream stays intact.
        try:
            r = await _capped(_render, s["path"], pair)
        except Exception as exc:
            return s, _item_error({"color": pair["color"], "material": pair["material"]}, exc)
        if not r.success or r.output_path is None:
            return s, _item_error({"color": pair["color"], "material": pair["material"]}, r)
        v_url, _vf, _vd = await _derived_url(r.output_path, output_format, qual, False)
        return s, {"color": pair["color"], "material": pair["material"],
                   "image_url": v_url, "generation_id": r.generation_id, "cost": r.actual_cost}

    total = len(usable) * len(pairs)

    async def _stream():
        meta = {
            "type": "meta", "total": total, "model": model,
            "sources": [{"sid": s["sid"], "source_kind": s["kind"], "source_ref": s["ref"],
                         "source_url": s.get("url"), "error": s.get("error")} for s in resolved],
        }
        yield json.dumps(meta) + "\n"
        total_cost = 0.0
        coros = [_job(s, pair) for s in usable for pair in pairs]
        for fut in asyncio.as_completed(coros):
            s, tile = await fut
            if "cost" in tile:
                total_cost += tile.get("cost", 0)
            yield json.dumps({"type": "tile", "sid": s["sid"], **tile}) + "\n"
        await asyncio.to_thread(_prune_storage)
        yield json.dumps({"type": "done", "total_cost": total_cost}) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@router.post("/api/regenerate-variant")
async def api_regenerate_variant(
    api_key: str = Form(""),
    kind: str = Form("sofa"),
    color: str = Form(""),
    material: str = Form("boucle"),
    color_custom: str = Form(""),
    mat_notes: str = Form(""),
    size: str = Form("3"),
    legs: str = Form("keep"),
    cam: str = Form("studio"),
    lens: str = Form("50mm_natural"),
    tod: str = Form("noon_neutral"),
    shadow: str = Form("soft_diffuse"),
    shot: str = Form(""),
    yaw: str = Form(""),
    height: str = Form(""),
    dof: str = Form(""),
    detail_region: str = Form(""),
    bedding: str = Form(""),
    bedding_custom: str = Form(""),
    throw: str = Form(""),
    tidy: str = Form(""),
    density: str = Form(""),
    accents: str = Form(""),
    bed_note: str = Form(""),
    model: str = Form("gemini-3.1-flash-image-preview"),
    aspect: str = Form("4:3"),
    res: str = Form("1K"),
    seed: str = Form(""),
    output_format: str = Form("jpg"),
    output_quality: str = Form("82"),
    # Source: a ref to an existing render OR a re-uploaded base photo.
    source_ref: str = Form(""),
    source_image: Optional[UploadFile] = File(None),
):
    """Re-render ONE (source × colour+material) tile in the same keep-scene recolor
    mode. Backs the per-tile 'regeneruj' button so a single bad render can be fixed
    without re-running the whole grid."""
    if not api_key.strip():
        return _validation_error("Brak klucza API.", "MISSING_API_KEY")
    if not color.strip():
        return _validation_error("Brak koloru wariantu.", "TOO_FEW_PAIRS")

    src_path: Optional[Path] = None
    if source_ref.strip():
        src_path = _resolve_anchor_path(source_ref)
        if src_path is None:
            return _validation_error("Nie znaleziono zdjęcia bazowego.", "ANCHOR_NOT_FOUND", status=404)
    elif source_image is not None:
        try:
            src_path = await _save_upload(source_image, suffix="_src")
        except Exception as exc:
            return _validation_error(f"Nie udało się odczytać zdjęcia: {exc}", "BAD_INPUT_IMAGE")
    else:
        return _validation_error("Brak zdjęcia bazowego.", "MISSING_SOURCES")

    bedding_desc = ""
    if kind == "bed":
        bedding_desc = _compose_bedding_description(
            bedding=bedding, bedding_custom=bedding_custom, throw=throw,
            tidy=tidy, density=density, accents_csv=accents, bed_note=bed_note,
        )
    req = _recolor_request(
        api_key=api_key, kind=kind, color=color, color_custom=color_custom,
        mat=material, mat_notes=mat_notes, size=size, legs=legs, cam=cam,
        lens=lens, tod=tod, shadow=shadow, shot=shot, yaw=yaw, height=height,
        dof=dof, detail_region=detail_region, model=model, aspect=aspect, res=res,
        seed=seed, bedding_desc=bedding_desc, source_path=src_path,
    )
    result = await asyncio.to_thread(generate, req)
    if not result.success or result.output_path is None:
        return _result_error(result)
    qual = _parse_quality(output_quality)
    url, _f, _d = await _derived_url(result.output_path, output_format, qual, False)
    await asyncio.to_thread(_prune_storage)
    return {"success": True, "color": color, "material": material, "image_url": url,
            "generation_id": result.generation_id, "cost": result.actual_cost}


@router.post("/api/generate-free")
async def api_generate_free(
    api_key: str = Form(""),
    openrouter_key: str = Form(""),
    prompt: str = Form(""),
    style: str = Form(""),
    env: str = Form(""),
    tod: str = Form(""),
    lens: str = Form(""),
    height: str = Form(""),
    color: str = Form(""),
    mat: str = Form(""),
    people: str = Form(""),
    model: str = Form("gemini-2.5-flash-image"),
    aspect: str = Form("4:3"),
    res: str = Form("1K"),
    seed: str = Form(""),
    output_format: str = Form("jpg"),
    output_quality: str = Form("82"),
    references: list[UploadFile] = File(default_factory=list),
):
    """Editorial mode: text-to-image, no base product photo. The brief plus
    optional picker fragments become the whole prompt (see
    _build_freeform_request); optional moodboard refs ride along. Gemini
    models run through the normal generate() pipeline; FLUX / Seedream run
    through the OpenRouter Images API with the user's OpenRouter key."""
    is_openrouter = model in OPENROUTER_MODELS
    if is_openrouter:
        if not openrouter_key.strip():
            return _validation_error(
                "Ten model działa przez OpenRouter — wklej klucz OpenRouter (sk-or-…).",
                "MISSING_OPENROUTER_KEY",
            )
    elif not api_key.strip():
        return _validation_error("Brak klucza API.", "MISSING_API_KEY")
    if len(prompt.strip()) < 3:
        return _validation_error("Opisz, co ma być na zdjęciu.", "MISSING_PROMPT")

    extra_ref_paths: list[Path] = []
    for idx, ref in enumerate(references or []):
        if ref is None:
            continue
        try:
            extra_ref_paths.append(await _save_upload(ref, suffix=f"_edref{idx}"))
        except Exception as exc:
            logger.warning("Editorial reference #%d unreadable, ignoring: %s", idx, exc)

    # The prompt text is composed identically for both engines — one wording,
    # two backends, comparable results.
    req = _build_freeform_request(
        api_key=api_key, text=prompt,
        style=style, env=env, tod=tod, lens=lens, height=height,
        color=color, mat=mat, people=people,
        model=model if not is_openrouter else "gemini-2.5-flash-image",
        aspect=aspect, res=res, seed=seed,
        extra_reference_paths=extra_ref_paths,
    )

    logger.info("Editorial generate: style=%s env=%s model=%s engine=%s",
                style or "-", env or "-", model, "openrouter" if is_openrouter else "google")

    if is_openrouter:
        try:
            out = await asyncio.to_thread(
                generate_openrouter,
                api_key=openrouter_key.strip(), model=model,
                prompt=req.freeform_prompt, aspect=aspect,
                ref_paths=extra_ref_paths,
            )
        except OpenRouterError as exc:
            return JSONResponse(
                {"error": exc.message_pl, "error_code": exc.code,
                 "detail_en": exc.detail, "retryable": exc.retryable},
                status_code=exc.http_status,
            )
        output_path, generation_id = out["output_path"], out["generation_id"]
        cost, model_used, elapsed_ms = out["cost"], out["model_id"], out["elapsed_ms"]
        resolution_used = "auto"
    else:
        result = await asyncio.to_thread(generate, req)
        if not result.success or result.output_path is None:
            return _result_error(result)
        output_path, generation_id = Path(result.output_path), result.generation_id
        cost, model_used, elapsed_ms = result.actual_cost, result.model_id, result.elapsed_ms
        resolution_used = result.resolution

    image_url, fmt_used, downgraded = await _derived_url(
        output_path, output_format, _parse_quality(output_quality),
        False,
    )
    await asyncio.to_thread(_prune_storage)

    return {
        "success": True,
        "generation_id": generation_id,
        "image_url": image_url,
        "format": fmt_used,
        "format_downgraded": downgraded,
        "cost": cost,
        "model": model_used,
        "resolution": resolution_used,
        "elapsed_ms": elapsed_ms,
    }
