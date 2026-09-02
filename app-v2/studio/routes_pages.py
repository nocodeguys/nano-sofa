"""Static pages, health/config/docs endpoints, output file serving, history."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.core.cost_tracker import recent_generations
from app.core.schema_loader import schema
from studio.catalog import CATALOG, _COLOR_PL_TO_EN, _MATERIAL_PL_TO_EN
from studio.mappings import (
    _ACCENT_TO_PROMPT,
    _BEDDING_TO_PROMPT,
    _DENSITY_TO_PROMPT,
    _DETAIL_REGION_TO_PHRASE,
    _DOF_TO_APERTURE,
    _ENV_TO_SCENE,
    _HEIGHT_TO_PHRASE,
    _LENS_TO_PROMPT,
    _SHADOW_TO_PROMPT,
    _SHOT_TYPE_TO_FRAMING,
    _THROW_TO_PROMPT,
    _TIDY_TO_PROMPT,
    _TOD_TO_PROMPT,
    _YAW_TO_ANGLE,
)
from studio.media import _MEDIA_TYPES, _read_png_meta
from studio.normalize import is_raw_copy as _is_raw
from studio.openrouter import OPENROUTER_MODELS
from studio.paths import _DIST_DIR, _OUTPUT_DIR, logger

router = APIRouter()


@router.get("/")
def index():
    return FileResponse(_DIST_DIR / "index.html")


@router.get("/editorial")
def editorial_page():
    return FileResponse(_DIST_DIR / "editorial.html")


@router.get("/experiments")
def experiments_page():
    return FileResponse(_DIST_DIR / "experiments.html")


@router.get("/catalog.js")
def catalog_js():
    # Synchronous script-tag bridge: data.jsx builds its COLORS/MATERIALS from
    # window.NS_CATALOG, so browser and server read the same catalog.json.
    # no-store — tiny file that must never be stale after a Watchtower update.
    body = "window.NS_CATALOG = " + json.dumps(CATALOG, ensure_ascii=False) + ";"
    return Response(
        content=body,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/help")
def help_page():
    # /docs is taken by FastAPI's Swagger UI, so the user guide lives at /help.
    return FileResponse(_DIST_DIR / "help.html")


@router.get("/healthz")
def healthz():
    """
    Liveness + capability report. No external calls. Used by Docker HEALTHCHECK
    and by the frontend on boot to confirm the server is ready.
    """
    return {
        "ok": True,
        "model_ids": list(schema.model_ids),
        "outputs_dir": str(_OUTPUT_DIR),
        "n_outputs": sum(1 for p in _OUTPUT_DIR.glob("*.png") if not _is_raw(p)),
    }


@router.get("/api/config")
def api_config():
    """
    Returns the model enum + per-model constraints so the frontend can render
    the model picker and disable invalid resolution / refs combinations.
    Source of truth: prompts/schemas/sofa.json (via app.core.schema_loader).
    """
    models = []
    model_labels = {
        "gemini-2.5-flash-image": "Nano Banana · legacy 1K",
        "gemini-3.1-flash-image": "Nano Banana 2 · polecany",
        "gemini-3-pro-image": "Nano Banana Pro · precyzja",
    }
    for mid in schema.model_ids:
        tier = "pro" if "pro" in mid else "flash"
        models.append({
            "id": mid,
            "label": model_labels.get(mid, mid),
            "tier": tier,
            "max_refs": schema.max_refs_for_model(mid),
            "max_resolution": schema.max_resolution_for_model(mid),
            "supports_resolution_param": schema.supports_resolution_param(mid),
            "resolutions": schema.resolution_choices_for_model(mid),
        })
    # Official Google guidance (updated 2026-08-26) recommends Nano Banana 2
    # as the general-purpose image model: stronger multi-reference consistency
    # and up to 4K output. Keep 2.5 only as a legacy fallback.
    preferred = "gemini-3.1-flash-image"
    default_id = (
        preferred
        if any(m["id"] == preferred for m in models)
        else (models[0]["id"] if models else None)
    )
    # Editorial tab: the Gemini models above plus the OpenRouter alternatives
    # (FLUX / Seedream) — text-to-image only, never offered in the variant
    # pipeline (the bake-off showed they don't preserve product geometry).
    editorial_models = [
        {**m, "provider": "google"} for m in models
    ] + [
        {
            "id": slug,
            "label": cfg["label"],
            "provider": "openrouter",
            "max_refs": cfg["max_refs"],
            "max_resolution": "auto",
            "supports_resolution_param": False,
            "resolutions": ["auto"],
            "price_hint": cfg.get("price_hint", ""),
            "aspects": cfg.get("aspects"),
        }
        for slug, cfg in OPENROUTER_MODELS.items()
    ]
    return {
        "models": models,
        "default_model": default_id,
        "editorial_models": editorial_models,
    }


@router.get("/api/eta")
def api_eta(model: str, resolution: str = "1K", refs: int = 0):
    """
    Estimated generation time for the given model/resolution/ref-count, so the
    frontend can show an honest ETA instead of a hardcoded constant. Returns
    measured p50/p90 from real history once enough renders accrue, otherwise a
    static seed estimate. Shape: {p50_s, p90_s, source, n}.
    """
    from app.core.cost_tracker import eta_for
    try:
        return eta_for(model, (resolution or "1K").split(" ")[0].strip().upper(), max(0, int(refs)))
    except Exception as exc:
        logger.warning("ETA lookup failed: %s", exc)
        return {"p50_s": 12.0, "p90_s": 24.0, "source": "fallback", "n": 0}


@router.get("/api/param-docs")
def api_param_docs():
    """
    Serialize the prompt mapping tables (the single source of truth for what
    each wizard parameter does) so the /help docs page can render, per option,
    the exact English clause the model receives. Keyed by the same id as the
    data.jsx NS_DATA tables, so the docs page joins these clauses with the
    Polish labels the UI shows — docs can't drift from behavior.
    """
    lens = {k: f"{v['focal_mm']} mm — {v['descriptor']}" for k, v in _LENS_TO_PROMPT.items()}
    shadow = {k: v["desc"] for k, v in _SHADOW_TO_PROMPT.items()}
    yaw = {k: f"{label} ({deg}° od osi)" for k, (label, deg) in _YAW_TO_ANGLE.items()}
    dof = {k: f"przysłona {v}" for k, v in _DOF_TO_APERTURE.items()}
    env = {k: f"[{mode}] {desc}" for k, (mode, desc) in _ENV_TO_SCENE.items()}

    groups = [
        {"key": "color",    "title": "Kolor obicia",        "table": "COLORS",        "clauses": dict(_COLOR_PL_TO_EN)},
        {"key": "material", "title": "Materiał",            "table": "MATERIALS",     "clauses": dict(_MATERIAL_PL_TO_EN)},
        {"key": "env",      "title": "Tło / sceneria",      "table": "ENVIRONMENTS",  "clauses": env},
        {"key": "shot",     "title": "Typ kadru",           "table": "SHOT_TYPES",    "clauses": dict(_SHOT_TYPE_TO_FRAMING)},
        {"key": "yaw",      "title": "Obrót / kąt kamery",  "table": "CAMERA_YAWS",   "clauses": yaw},
        {"key": "height",   "title": "Wysokość kamery",     "table": "CAMERA_HEIGHTS","clauses": dict(_HEIGHT_TO_PHRASE)},
        {"key": "dof",      "title": "Głębia ostrości",     "table": "DEPTHS_OF_FIELD","clauses": dof},
        {"key": "lens",     "title": "Obiektyw",            "table": "LENSES",        "clauses": lens},
        {"key": "tod",      "title": "Pora dnia / światło", "table": "TIMES_OF_DAY",  "clauses": dict(_TOD_TO_PROMPT)},
        {"key": "shadow",   "title": "Cień",                "table": "SHADOWS",       "clauses": shadow},
        {"key": "detail_fabric", "title": "Detal — makro tkaniny", "table": "DETAIL_REGIONS_FABRIC", "clauses": dict(_DETAIL_REGION_TO_PHRASE)},
        {"key": "detail_corner", "title": "Detal — narożnik / szew", "table": "DETAIL_REGIONS_CORNER", "clauses": dict(_DETAIL_REGION_TO_PHRASE)},
        {"key": "bedding",  "title": "Pościel (łóżka)",     "table": "BEDDING_PRESETS","clauses": dict(_BEDDING_TO_PROMPT)},
        {"key": "throw",    "title": "Narzuta / koc",       "table": "THROW_PRESETS", "clauses": dict(_THROW_TO_PROMPT)},
        {"key": "tidy",     "title": "Zaścielenie",         "table": "TIDY_LEVELS",   "clauses": dict(_TIDY_TO_PROMPT)},
        {"key": "density",  "title": "Gęstość stylizacji",  "table": "DENSITY_LEVELS","clauses": dict(_DENSITY_TO_PROMPT)},
        {"key": "accents",  "title": "Dodatki dekoracyjne", "table": "BED_ACCENTS",   "clauses": dict(_ACCENT_TO_PROMPT)},
    ]
    return {"groups": groups}


@router.get("/api/outputs/{name}")
def get_output(name: str):
    # Basename-only + parent check prevents path traversal (e.g. "../../etc/..."
    # or an absolute name) — this route only ever serves files that live
    # directly in _OUTPUT_DIR.
    candidate = (_OUTPUT_DIR / Path(name).name).resolve()
    if candidate.parent != _OUTPUT_DIR or not candidate.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(candidate, media_type=_MEDIA_TYPES.get(candidate.suffix.lower()))


@router.get("/api/history")
def api_history(limit: int = 60):
    """Past renders on disk (newest first), self-describing via embedded metadata.

    Powers the Fotosesja "Historia" anchor browser. Read-only; no API key needed.
    Lists the master PNGs under _OUTPUT_DIR and reads each one's identity straight
    from its tEXt chunks (the embed written at generate time), enriching from the
    cost DB only for older files that predate the embed. This is robust to a
    stale/foreign cost DB — every file the user can see is pickable as an anchor.
    Each item is reusable via /api/generate-variants by its generation_id.
    """
    limit = max(1, min(int(limit or 60), 200))

    # Index the cost DB by output basename to enrich files lacking embedded meta.
    db_by_name: dict = {}
    try:
        for rec in recent_generations(800):
            op = rec.get("output_path")
            if op:
                db_by_name.setdefault(Path(op).name, rec)
    except Exception:
        pass

    # Master PNGs live directly under _OUTPUT_DIR (uploads are in a subdir;
    # derived jpg/webp aren't .png). The pre-normalization .raw.png kept beside
    # each normalized master is a diagnostic copy, not a render — listing it
    # would show every catalog shot twice. Newest first by mtime.
    try:
        masters = [p for p in _OUTPUT_DIR.glob("*.png") if p.is_file() and not _is_raw(p)]
    except Exception:
        masters = []
    masters.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    items: list[dict] = []
    for p in masters[:limit]:
        meta = _read_png_meta(p)
        rec = db_by_name.get(p.name, {})
        ts_raw = meta.get("nano_sofa_ts", "")
        items.append({
            "generation_id": meta.get("nano_sofa_generation_id") or rec.get("generation_id"),
            "image_url": f"/api/outputs/{p.name}",
            "color": meta.get("nano_sofa_color") or rec.get("upholstery_color"),
            "material": meta.get("nano_sofa_material") or rec.get("upholstery_material"),
            "model": meta.get("nano_sofa_model") or rec.get("model_id"),
            "resolution": meta.get("nano_sofa_resolution") or rec.get("resolution"),
            "camera_angle": meta.get("nano_sofa_camera_angle") or rec.get("camera_angle"),
            "prompt_summary": meta.get("nano_sofa_prompt_summary") or rec.get("prompt_summary"),
            "ts": int(ts_raw) if ts_raw.isdigit() else rec.get("timestamp"),
        })
    return {"items": items}


@router.get("/api/experiments")
def api_experiments(limit: int = 120):
    """Generation runs prepared for visual A/B comparison.

    New renders are backed by full key-free manifests. Older DB rows are kept
    visible as legacy runs, but are explicitly marked as incomplete so the UI
    never implies that their prompts or references were verified as identical.
    """
    limit = max(2, min(int(limit or 120), 300))
    trace_dir = _OUTPUT_DIR / "traces"
    trace_paths = sorted(
        (p for p in trace_dir.glob("*.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ) if trace_dir.is_dir() else []

    try:
        legacy_rows = recent_generations(limit * 2)
    except Exception:
        legacy_rows = []
    db_by_id = {
        str(rec.get("generation_id")): rec
        for rec in legacy_rows if rec.get("generation_id")
    }

    items: list[dict] = []
    seen_ids: set[str] = set()
    for path in trace_paths[:limit]:
        try:
            trace = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        generation_id = str(trace.get("generation_id") or "")
        if not generation_id:
            continue
        seen_ids.add(generation_id)
        rec = db_by_id.get(generation_id, {})
        result = trace.get("result") or {}
        variant = trace.get("variant") or {}
        output_name = Path(str(result.get("output_path") or "")).name
        output_file = _OUTPUT_DIR / output_name if output_name else None
        references = [
            {
                "slot": ref.get("slot"),
                "role": ref.get("role"),
                "filename": Path(str(ref.get("source") or "")).name,
                "sha256": ref.get("sha256_rgb"),
                "width": ref.get("width"),
                "height": ref.get("height"),
            }
            for ref in (trace.get("references") or [])
        ]
        items.append({
            "generation_id": generation_id,
            "tracked": True,
            "created_at": trace.get("created_at") or path.stat().st_mtime,
            "status": trace.get("status"),
            "model": trace.get("model_id"),
            "resolution": trace.get("resolution"),
            "aspect_ratio": trace.get("aspect_ratio"),
            "prompt": trace.get("prompt") or "",
            "prompt_sha256": trace.get("prompt_sha256"),
            "setup_fingerprint": trace.get("setup_fingerprint"),
            "exact_fingerprint": trace.get("exact_fingerprint"),
            "references": references,
            "elapsed_ms": result.get("elapsed_ms"),
            "actual_cost": result.get("actual_cost"),
            "attempts": result.get("attempts"),
            "material": variant.get("material") or rec.get("upholstery_material"),
            "color": variant.get("color") or rec.get("upholstery_color"),
            "prompt_summary": rec.get("prompt_summary"),
            "image_url": (
                f"/api/outputs/{output_name}"
                if output_file and output_file.is_file() else None
            ),
        })

    # Backfill the screen with older renders. These remain useful visually,
    # while `tracked=False` prevents them from being treated as controlled A/B.
    if len(items) < limit:
        for rec in legacy_rows:
            generation_id = str(rec.get("generation_id") or "")
            if not generation_id or generation_id in seen_ids:
                continue
            output_name = Path(str(rec.get("output_path") or "")).name
            output_file = _OUTPUT_DIR / output_name if output_name else None
            if not output_file or not output_file.is_file():
                continue
            items.append({
                "generation_id": generation_id,
                "tracked": False,
                "created_at": rec.get("timestamp"),
                "status": rec.get("status"),
                "model": rec.get("model_id"),
                "resolution": rec.get("resolution"),
                "aspect_ratio": None,
                "prompt": "",
                "prompt_sha256": None,
                "setup_fingerprint": None,
                "exact_fingerprint": None,
                "references": [],
                "elapsed_ms": rec.get("elapsed_ms"),
                "actual_cost": rec.get("actual_cost"),
                "attempts": None,
                "material": rec.get("upholstery_material"),
                "color": rec.get("upholstery_color"),
                "prompt_summary": rec.get("prompt_summary"),
                "image_url": f"/api/outputs/{output_name}",
            })
            if len(items) >= limit:
                break

    items.sort(key=lambda item: item.get("created_at") or 0, reverse=True)
    return {
        "items": items[:limit],
        "tracked_count": sum(1 for item in items[:limit] if item["tracked"]),
        "legacy_count": sum(1 for item in items[:limit] if not item["tracked"]),
    }
