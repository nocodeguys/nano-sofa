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
from studio.paths import _DIST_DIR, _OUTPUT_DIR, logger

router = APIRouter()


@router.get("/")
def index():
    return FileResponse(_DIST_DIR / "index.html")


@router.get("/editorial")
def editorial_page():
    return FileResponse(_DIST_DIR / "editorial.html")


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
        "n_outputs": sum(1 for p in _OUTPUT_DIR.glob("*.png")),
    }


@router.get("/api/config")
def api_config():
    """
    Returns the model enum + per-model constraints so the frontend can render
    the model picker and disable invalid resolution / refs combinations.
    Source of truth: prompts/schemas/sofa.json (via app.core.schema_loader).
    """
    models = []
    for mid in schema.model_ids:
        tier = "pro" if "pro" in mid else "flash"
        models.append({
            "id": mid,
            "label": mid,
            "tier": tier,
            "max_refs": schema.max_refs_for_model(mid),
            "max_resolution": schema.max_resolution_for_model(mid),
            "supports_resolution_param": schema.supports_resolution_param(mid),
            "resolutions": schema.resolution_choices_for_model(mid),
        })
    # Default model preference: prefer Nano Banana 2 (3.1-flash-image-preview)
    # for its richer scene adherence, 14-ref cap, and 4K resolution support
    # over the GA 2.5-flash-image (which deprecates 2026-10-02). Fall back to
    # the first model in the enum if 3.1 isn't available.
    preferred = "gemini-3.1-flash-image-preview"
    default_id = (
        preferred
        if any(m["id"] == preferred for m in models)
        else (models[0]["id"] if models else None)
    )
    return {
        "models": models,
        "default_model": default_id,
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
    # derived jpg/webp aren't .png). Newest first by mtime.
    try:
        masters = [p for p in _OUTPUT_DIR.glob("*.png") if p.is_file()]
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
