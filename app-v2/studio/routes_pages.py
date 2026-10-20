"""Static pages, health/config/docs endpoints, output file serving, history."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.core.cost_tracker import recent_generations
from app.core.model_registry import registry
from app.core.schema_loader import schema


def _model_short(model_id: str | None) -> str:
    m = registry.get(model_id or "")
    return m.short if m else (model_id or "—")
from studio.catalog import CATALOG, _COLOR_PL_TO_EN, _MATERIAL_PL_TO_EN, catalog_for_browser
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
from studio.paths import _DIST_DIR, _OUTPUT_DIR, logger, page_response

router = APIRouter()


@router.get("/")
def index():
    return page_response("index.html")


@router.get("/editorial")
def editorial_page():
    return page_response("editorial.html")


@router.get("/lab")
def lab_page():
    """Experimental tab: the product wizard (same bundle as the studio page,
    `data-mode="lab"`) driven by the OpenAI Images API — GPT Image 2.5 Flare /
    Sunburst with the user's own OpenAI key."""
    return page_response("lab.html")


@router.get("/experiments")
def experiments_page():
    return page_response("experiments.html")


@router.get("/catalog.js")
def catalog_js():
    # Synchronous script-tag bridge: data.jsx builds its COLORS/MATERIALS from
    # window.NS_CATALOG, so browser and server read the same catalog.json.
    # no-store — tiny file that must never be stale after a Watchtower update.
    body = "window.NS_CATALOG = " + json.dumps(catalog_for_browser(), ensure_ascii=False) + ";"
    return Response(
        content=body,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/catalog-status")
def catalog_status():
    """Cheap, public: lets an open studio tab notice that the catalogue changed
    (poll on focus, reload when `version` differs) and shows which materials
    have curated reference photos on this instance."""
    from studio.paths import _CATALOG_PATH, _MATERIAL_REFS_DIR

    references: dict[str, dict[str, bool]] = {}
    for material in CATALOG.get("materials", []):
        mid = material["id"]
        names = {p.stem for p in _MATERIAL_REFS_DIR.glob(f"{mid}*") if p.is_file()} if _MATERIAL_REFS_DIR.is_dir() else set()
        references[mid] = {
            "macro": mid in names,
            "left": f"{mid}-left" in names,
            "right": f"{mid}-right" in names,
            "behavior": f"{mid}-behavior" in names,
            "application": f"{mid}-application" in names,
        }
    try:
        version = str(_CATALOG_PATH.stat().st_mtime_ns)
    except OSError:
        version = "0"
    return Response(
        content=json.dumps({"version": version, "references": references}),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/help")
def help_page():
    # /docs is taken by FastAPI's Swagger UI, so the user guide lives at /help.
    return page_response("help.html")


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
    The model catalogue for every page, straight from app-v2/models.json:
    `models` (studio wizard, Gemini), `lab_models` (wizard on OpenAI),
    `editorial_models` (freeform: Gemini + OpenRouter + OpenAI), the default
    per surface, and the ETA seeds. Every entry carries the reference cap,
    moodboard limit, resolutions, aspects, quality tiers and a per-resolution
    price so the UI never hard-codes any of it. Deprecated models are listed
    with `deprecated: true` so an old preset still resolves, never as default.
    """
    return registry.config_payload()


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
            "color_id": meta.get("nano_sofa_color_id") or None,
            "material_id": meta.get("nano_sofa_material_id") or None,
            "fabric_code": meta.get("nano_sofa_fabric_code") or None,
            "color_hex": meta.get("nano_sofa_color_hex") or None,
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
            "model_label": _model_short(trace.get("model_id")),
            "tier": registry.tier_of(trace.get("model_id") or ""),
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
            "material_id": variant.get("material_id") or None,
            "color_id": variant.get("color_id") or None,
            "fabric_code": variant.get("fabric_code") or None,
            "color_hex": variant.get("color_hex") or None,
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
                "model_label": _model_short(rec.get("model_id")),
                "tier": registry.tier_of(rec.get("model_id") or ""),
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
