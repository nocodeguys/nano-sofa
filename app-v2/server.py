"""
server.py — FastAPI backend for Nano Sofa Studio v2.

Serves the static React/HTML/CSS prototype from ./static and exposes:
  GET  /                   → Nano Sofa Studio v2.html (current design)
  GET  /v1                 → Nano Sofa Studio.html   (earlier design, static)
  GET  /healthz            → liveness + capability report (no API call)
  GET  /api/config         → model enum + per-model constraints
  POST /api/generate       → run a single generation
  GET  /api/outputs/<file> → serve a generated image

Wraps app/core/generator.py from the parent project (shared with v1).

Environment variables:
  PORT          listen port (default 7861)
  HOST          listen host (default 0.0.0.0)
  OUTPUTS_DIR   where generated images and uploads live (default <repo>/outputs)
                Mount this as a volume in Docker to persist renders.

Run with:
    cd <repo-root> && python app-v2/server.py
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
import uuid
from dataclasses import replace as dataclass_replace
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

# Make the parent project importable so we reuse app.core.generator
_THIS = Path(__file__).resolve().parent
_REPO_ROOT = _THIS.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.core.generator import GenerationRequest, generate  # noqa: E402
from app.core.schema_loader import schema  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nano-sofa-v2")

# ---------------------------------------------------------------------------
# Mappings: React state → GenerationRequest
# ---------------------------------------------------------------------------

# Polish color name (from data.jsx COLORS) → English term the prompt uses.
_COLOR_PL_TO_EN = {
    "saliw": "sage green",
    "ecru": "ecru off-white",
    "carmel": "warm caramel brown",
    "graphi": "graphite charcoal",
    "rust": "rust orange",
    "cream": "cream",
    "navy": "deep navy blue",
    "moos": "moss green",
    "rose": "dusty powder pink",
    "stone": "warm stone beige",
    "choc": "chocolate brown",
    "blush": "peach blush",
}

_MATERIAL_PL_TO_EN = {
    "boucle": "bouclé",
    "velvet": "velvet",
    "linen": "linen",
    "weave": "flat woven fabric",
    "chenille": "chenille",
    "leather": "smooth leather",
}

_CAMERA_TO_ANGLE = {
    "studio": ("front-34-left", 35),
    "lounge": ("front-34-right", 40),
    "loft": ("front-34-left", 30),
    "detail": ("close-detail", 0),
    "eye": ("eye-level-front", 0),
    "top": ("top-down-45", 0),
}

_SOFA_CONFIG = {
    "1": "armchair",
    "2": "2-seater",
    "3": "3-seater",
    "4": "4-seater",
    "L": "L-shaped sectional",
    "U": "U-shaped sectional",
}
_BED_CONFIG = {"90": "90x200 single", "120": "120x200 french", "140": "140x200 double",
               "160": "160x200 queen", "180": "180x200 king"}

_LEG_TO_ID = {
    "keep": None,
    "wood": "tapered-wood",
    "metal": "hairpin-metal",
    "block": "block-wood",
    "hidden": "plinth-hidden",
    "swivel": "swivel-base",
}

# Cyclorama profile — locked multi-sentence spec. The packshot SCENE block
# in generator.py emits this verbatim when env_mode == "packshot". The level
# of detail is intentional: the loose one-liner ("clean white studio
# cyclorama") used to allow the model to reinterpret the backdrop on every
# render, which is exactly the inconsistency the user reported. With a fixed
# RGB, an explicit no-horizon-line clause, and a specific contact-shadow
# description, every packshot lands on the same look.
_CYCLORAMA_PROFILES = {
    "cyclorama_warm": (
        "a seamless infinity-curve studio cyclorama in warm off-white, base "
        "tone RGB(244,240,229) hex #F4F0E5 (the catalog warm cream used by "
        "premium European furniture brands). The backdrop has no visible "
        "horizon line between floor and wall — the curve is completely "
        "seamless. CRITICAL LIGHTING DETAIL: the cyclorama is NOT flat. "
        "A large overhead soft-box creates a visible, soft top-down "
        "lighting wash on the backdrop — the upper portion of the curve "
        "is fractionally brighter (about RGB 250,247,238) than the base "
        "tone, and the brightness fades gently toward the floor and the "
        "edges. This subtle top-light gradient is what gives the cyclorama "
        "dimension; without it the backdrop looks dead. SHADOW SPEC: a "
        "small, soft, anchored contact shadow sits directly beneath the "
        "product. Shadow color is a warm mid-grey RGB(200,195,180) — not "
        "black. Shadow edges are heavily blurred (gaussian-soft, no harsh "
        "silhouette). The shadow has zero directional cast — it is an "
        "anchor shadow only, not a thrown shadow. The shadow fades to "
        "invisibility within roughly 25 centimeters of the product's "
        "contact line with the floor. The floor under the product has a "
        "very subtle darkening gradient at the contact line, fading to the "
        "full backdrop tone within 30 centimeters. Absolutely no props, "
        "no walls, no floor seams, no environment objects, no other "
        "furniture, no plants, no rugs, no signage"
    ),
    "cyclorama_neutral": (
        "a seamless infinity-curve studio cyclorama in clean neutral white, "
        "base tone RGB(250,250,250) hex #FAFAFA (pure photo-studio white, "
        "no warm or cool tint). Otherwise identical to the warm cyclorama "
        "profile: seamless floor-to-wall curve, no horizon line. CRITICAL "
        "LIGHTING DETAIL: a large overhead soft-box creates a visible, "
        "soft top-down lighting wash on the backdrop — the upper portion "
        "of the curve is fractionally brighter (about RGB 255,255,255) "
        "than the base tone, fading gently toward the floor and edges. "
        "The gradient is subtle but visible — the cyclorama is not flat. "
        "SHADOW SPEC: small soft anchored contact shadow in mid-grey "
        "RGB(210,210,210), heavily blurred edges, zero directional cast, "
        "fading to invisibility within 25 cm of the contact line. Subtle "
        "floor darkening at the contact line, fading within 30 cm. No "
        "props, no walls, no environment objects of any kind"
    ),
    "cyclorama_grey": (
        "a seamless infinity-curve studio cyclorama in neutral mid-grey, "
        "base tone RGB(220,220,220) hex #DCDCDC (packshot grey, slightly "
        "cooler than neutral white). Seamless floor-to-wall curve, no "
        "horizon line. CRITICAL LIGHTING DETAIL: visible soft top-down "
        "lighting wash — upper portion of the curve fractionally brighter "
        "(about RGB 235,235,235) than the base tone, fading toward floor "
        "and edges. The cyclorama is not flat. SHADOW SPEC: small soft "
        "anchored contact shadow in darker grey RGB(180,180,180), heavily "
        "blurred edges, zero directional cast, fading within 25 cm. "
        "Subtle floor darkening at the contact line. No props, no walls, "
        "no environment objects"
    ),
    "cyclorama_transparent": (
        "transparent background output (alpha PNG) — the product is isolated "
        "with no backdrop at all. Render only the product with a small soft "
        "warm-grey contact shadow beneath it (RGB 200,195,180, heavily "
        "blurred, no directional cast); everything else is fully transparent. "
        "No floor, no wall, no environment, no other objects"
    ),
}

# Environment id (from data.jsx ENVIRONMENTS) → (mode, scene description).
# Mode drives the two branches of the SCENE block in generator.py:
#   "packshot"  → product on a clean backdrop, no room context.
#   "lifestyle" → product staged inside a real interior, environment first-class.
_ENV_TO_SCENE = {
    # Cyclorama presets — locked profiles that always look the same.
    "cyclorama_warm":        ("packshot", _CYCLORAMA_PROFILES["cyclorama_warm"]),
    "cyclorama_neutral":     ("packshot", _CYCLORAMA_PROFILES["cyclorama_neutral"]),
    "cyclorama_grey":        ("packshot", _CYCLORAMA_PROFILES["cyclorama_grey"]),
    "cyclorama_transparent": ("packshot", _CYCLORAMA_PROFILES["cyclorama_transparent"]),
    # Legacy aliases — point at the new locked profiles so existing wizard
    # users automatically inherit the consistency upgrade.
    "studio_white":          ("packshot", _CYCLORAMA_PROFILES["cyclorama_warm"]),
    "studio_grey":           ("packshot", _CYCLORAMA_PROFILES["cyclorama_grey"]),
    "transparent":           ("packshot", _CYCLORAMA_PROFILES["cyclorama_transparent"]),
    # Lifestyle envs — unchanged narrative descriptions.
    "scandi":        ("lifestyle", "a scandinavian living room with light oak floors, white walls, and indoor plants"),
    "loft":          ("lifestyle", "an industrial loft with exposed brick walls, polished concrete floors, and dark metal accents"),
    "japandi":       ("lifestyle", "a japandi interior with a warm minimalist palette, natural wood, and soft diffuse light"),
    "boho":          ("lifestyle", "a bohemian living room with rattan furniture, woven textiles, and warm earthy tones"),
    "dark_moody":    ("lifestyle", "a moody dark interior with deep painted walls and warm pendant lamp lighting"),
    "garden":        ("lifestyle", "an outdoor terrace / garden setting with greenery and natural daylight"),
    "showroom":      ("lifestyle", "a brand showroom with subtle product staging and a neutral palette"),
    "custom":        ("lifestyle", "the custom interior shown in the user's uploaded background reference image"),
}

# Canonical key is the English `id` from data.jsx (LENSES / TIMES_OF_DAY /
# SHADOWS). Polish display strings are accepted too for backward compatibility
# with browser caches that still hold the pre-2026-05 UI — see the alias
# tables below. Once we trust everyone is on the new build these aliases can
# be deleted.

# English id → English narrative for time-of-day / lighting quality.
# Feeds GenerationRequest.tod_description, which lands inside the SCENE block.
_TOD_TO_PROMPT = {
    "morning_cool": "early morning cool soft light, approximately 4500 K, low-angle long shadows from one side",
    "noon_neutral": "midday neutral daylight, approximately 5500 K, overhead light with short even shadows",
    "golden_hour":  "golden-hour warm directional light, approximately 3000 K, long warm shadows, golden cast across the scene",
    "evening_lamp": "evening warm artificial lamp lighting, approximately 2800 K, low ambient light with pools of warm illumination",
}
_TOD_LEGACY_ALIAS = {
    "poranek — chłodne, miękkie":  "morning_cool",
    "południe — neutralne":         "noon_neutral",
    "złota godzina — ciepłe":       "golden_hour",
    "wieczór — lampy":              "evening_lamp",
}

# English id → focal length + intent descriptor.
# Captures lens *intent* (catalog / product / wide) that focal length alone discards.
_LENS_TO_PROMPT = {
    "35mm_wide":    {"focal_mm": 35, "descriptor": "35 mm wide-angle, includes generous environment context, slight perspective exaggeration"},
    "50mm_natural": {"focal_mm": 50, "descriptor": "50 mm natural perspective, matches the human eye, standard catalog framing"},
    "85mm_product": {"focal_mm": 85, "descriptor": "85 mm short telephoto, mild background compression, flattering product photography standard"},
}
_LENS_LEGACY_ALIAS = {
    "35 mm — szeroki kontekst": "35mm_wide",
    "50 mm — naturalna":         "50mm_natural",
    "85 mm — produktowa":        "85mm_product",
}
_LENS_DEFAULT = {"focal_mm": 50, "descriptor": "50 mm natural perspective, standard catalog framing"}

# English id → (clock-position direction, full English description).
# `direction` keeps backward compat with the existing shadow_direction field;
# `desc` is the narrative sentence that flows into the SCENE block.
_SHADOW_TO_PROMPT = {
    "soft_diffuse":  {"direction": "soft diffuse",
                      "desc": "soft diffuse shadow beneath the product, no strong directional cast, soft-box lighting quality"},
    "directional_4": {"direction": "4 o-clock",
                      "desc": "directional shadow falling toward 4 o-clock, suggesting window light from the upper left"},
    "hard_studio_5": {"direction": "5 o-clock",
                      "desc": "hard-edged shadow falling toward 5 o-clock, suggesting a studio strobe from the upper right"},
}
_SHADOW_LEGACY_ALIAS = {
    "miękkie rozproszone": "soft_diffuse",
    "kierunkowe — okno":   "directional_4",
    "twarde — studio":     "hard_studio_5",
}
_SHADOW_DEFAULT = {"direction": "soft diffuse",
                   "desc": "soft diffuse shadow beneath the product, no strong directional cast"}


def _resolve_id(value: str, aliases: dict) -> str:
    """Map a possibly-legacy Polish UI string to its English id; pass through ids unchanged."""
    if not value:
        return value
    return aliases.get(value, value)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Nano Sofa Studio v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_STATIC_DIR = _THIS  # serve prototype files from app-v2/

# OUTPUTS_DIR is the volume mount target in Docker. We keep generator outputs
# and per-request uploads under it so a single bind mount captures everything.
# Falls back to <repo>/outputs for local dev (matches the v1 layout).
_OUTPUT_DIR = Path(os.environ.get("OUTPUTS_DIR") or (_REPO_ROOT / "outputs")).resolve()
_UPLOAD_DIR = _OUTPUT_DIR / "v2-uploads"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Curated scene-reference images live alongside the app, baked into the Docker
# image at /app/app-v2/scene-references/<env_id>.{jpg,png,jpeg}. The lookup is
# best-effort — if no reference is found for an env_id, the prompt falls back
# to the text-only profile.
_SCENE_REFS_DIR = _THIS / "scene-references"


def _scene_reference_path(env_id: str) -> Optional[Path]:
    """Return the curated reference image path for an env id, if one exists."""
    if not env_id:
        return None
    for ext in (".jpg", ".jpeg", ".png"):
        candidate = _SCENE_REFS_DIR / f"{env_id}{ext}"
        if candidate.is_file():
            return candidate
    return None

# Override the generator's hardcoded outputs dir so it writes to the volume too.
# generator.py reads its dir at import time, so this must run before any call.
try:
    from app.core import generator as _gen_mod
    _gen_mod._OUTPUTS_DIR = _OUTPUT_DIR
except Exception:
    pass


@app.get("/")
def index():
    return FileResponse(_STATIC_DIR / "Nano Sofa Studio v2.html")


@app.get("/v1")
def index_v1():
    return FileResponse(_STATIC_DIR / "Nano Sofa Studio.html")


@app.get("/healthz")
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


@app.get("/api/config")
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


@app.get("/api/outputs/{name}")
def get_output(name: str):
    candidate = _OUTPUT_DIR / name
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(candidate)


def _build_generation_request(
    *,
    api_key: str,
    kind: str,
    color: str, color_custom: str,
    mat: str, mat_notes: str,
    size: str,
    legs: str,
    cam: str,
    lens: str, tod: str, shadow: str,
    env: str, env_note: str, env_mode: str,
    model: str, aspect: str, res: str, seed: str,
    base_image_path: Path,
    scene_image_path: Optional[Path],
    preserve_camera_from_base: bool = False,
) -> GenerationRequest:
    """
    Translate a parsed FormData payload into a GenerationRequest.
    Shared by /api/generate (single render) and /api/generate-set (color batch).
    Resolves legacy Polish strings via the alias tables so stale browser caches
    keep working.
    """
    upholstery_color = (
        color_custom.strip()
        if color == "custom" and color_custom.strip()
        else _COLOR_PL_TO_EN.get(color, "neutral")
    )
    upholstery_material = _MATERIAL_PL_TO_EN.get(mat, "fabric")

    is_bed = kind == "bed"
    sofa_config = (_BED_CONFIG if is_bed else _SOFA_CONFIG).get(size, "3-seater")
    camera_angle, deg = _CAMERA_TO_ANGLE.get(cam, ("front-34-left", 35))

    lens_id   = _resolve_id(lens,   _LENS_LEGACY_ALIAS)
    tod_id    = _resolve_id(tod,    _TOD_LEGACY_ALIAS)
    shadow_id = _resolve_id(shadow, _SHADOW_LEGACY_ALIAS)

    lens_data       = _LENS_TO_PROMPT.get(lens_id, _LENS_DEFAULT)
    shadow_data     = _SHADOW_TO_PROMPT.get(shadow_id, _SHADOW_DEFAULT)
    tod_description = _TOD_TO_PROMPT.get(tod_id, "")
    env_mode_label, env_description = _ENV_TO_SCENE.get(env, ("packshot", "neutral grey studio backdrop"))

    res_token = (res or "1K").split(" ")[0].strip().upper()
    resolution = res_token if res_token in ("1K", "2K", "4K") else "1K"

    leg_count = 0 if is_bed and legs == "keep" else 4
    leg_id = _LEG_TO_ID.get(legs)

    notes_parts = []
    if env_note.strip(): notes_parts.append(f"environment note: {env_note.strip()}")
    if env_mode.strip(): notes_parts.append(f"environment use: {env_mode.strip()}")
    if seed.strip():     notes_parts.append(f"seed hint: {seed.strip()}")

    return GenerationRequest(
        model_id=model,
        base_product_image=str(base_image_path),
        scene_reference_image=str(scene_image_path) if scene_image_path else None,
        product_type="bed" if is_bed else "sofa",
        sofa_configuration=sofa_config,
        leg_count=leg_count,
        preserve_list=["frame_silhouette", "stitching"],
        upholstery_color=upholstery_color,
        upholstery_material=upholstery_material,
        texture_notes=mat_notes.strip(),
        leg_id=leg_id,
        camera_angle=camera_angle,
        angle_degrees_from_left=deg,
        shadow_direction=shadow_data["direction"],
        focal_length_mm=lens_data["focal_mm"],
        lens_descriptor=lens_data["descriptor"],
        tod_description=tod_description,
        shadow_description=shadow_data["desc"],
        env_mode=env_mode_label,
        env_description=env_description,
        preserve_camera_from_base=preserve_camera_from_base,
        aspect_ratio=aspect,
        resolution=resolution,
        notes=" | ".join(notes_parts),
        api_key=api_key.strip(),
    )


async def _save_upload(upload: UploadFile, suffix: str = "") -> Path:
    """Read an UploadFile, decode as image, save as PNG under the uploads dir."""
    raw = await upload.read()
    pil = Image.open(io.BytesIO(raw))
    pil.load()
    out = _UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}.png"
    pil.convert("RGB").save(out, format="PNG")
    return out


@app.post("/api/generate")
async def api_generate(
    api_key: str = Form(""),
    kind: str = Form("sofa"),
    color: str = Form("saliw"),
    color_custom: str = Form(""),
    mat: str = Form("boucle"),
    mat_notes: str = Form(""),
    size: str = Form("3"),
    legs: str = Form("keep"),
    cam: str = Form("studio"),
    lens: str = Form("50mm_natural"),
    tod: str = Form("noon_neutral"),
    shadow: str = Form("soft_diffuse"),
    env: str = Form(""),
    env_note: str = Form(""),
    env_mode: str = Form(""),
    model: str = Form("gemini-2.5-flash-image"),
    aspect: str = Form("4:3"),
    res: str = Form("1K"),
    seed: str = Form(""),
    base_image: Optional[UploadFile] = File(None),
    scene_image: Optional[UploadFile] = File(None),
):
    if not api_key.strip():
        return JSONResponse({"error": "Brak klucza API."}, status_code=400)
    if base_image is None:
        return JSONResponse({"error": "Brak zdjęcia bazowego."}, status_code=400)

    try:
        upload_path = await _save_upload(base_image)
    except Exception as exc:
        return JSONResponse({"error": f"Nie udało się odczytać obrazu: {exc}"}, status_code=400)

    scene_upload_path: Optional[Path] = None
    if scene_image is not None:
        try:
            scene_upload_path = await _save_upload(scene_image, suffix="_scene")
        except Exception as exc:
            logger.warning("Scene reference image unreadable, ignoring: %s", exc)

    req = _build_generation_request(
        api_key=api_key, kind=kind,
        color=color, color_custom=color_custom,
        mat=mat, mat_notes=mat_notes,
        size=size, legs=legs, cam=cam,
        lens=lens, tod=tod, shadow=shadow,
        env=env, env_note=env_note, env_mode=env_mode,
        model=model, aspect=aspect, res=res, seed=seed,
        base_image_path=upload_path,
        scene_image_path=scene_upload_path,
    )

    logger.info("Generating: %s / %s / %s", req.upholstery_color, req.upholstery_material, req.camera_angle)
    result = generate(req)

    if not result.success or result.output_path is None:
        return JSONResponse(
            {"error": result.error_message or "Nieznany błąd generowania.",
             "attempts": result.attempts},
            status_code=500,
        )

    return {
        "success": True,
        "generation_id": result.generation_id,
        "image_url": f"/api/outputs/{result.output_path.name}",
        "cost": result.actual_cost,
        "model": result.model_id,
        "resolution": result.resolution,
    }


@app.post("/api/generate-set")
async def api_generate_set(
    api_key: str = Form(""),
    kind: str = Form("sofa"),
    colors_csv: str = Form(""),     # comma-separated English color ids (anchor first)
    color_custom: str = Form(""),
    mat: str = Form("boucle"),
    mat_notes: str = Form(""),
    size: str = Form("3"),
    legs: str = Form("keep"),
    cam: str = Form("studio"),
    lens: str = Form("50mm_natural"),
    tod: str = Form("noon_neutral"),
    shadow: str = Form("soft_diffuse"),
    env: str = Form(""),
    env_note: str = Form(""),
    env_mode: str = Form(""),
    model: str = Form("gemini-3.1-flash-image-preview"),
    aspect: str = Form("4:3"),
    res: str = Form("1K"),
    seed: str = Form(""),
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
        return JSONResponse({"error": "Brak klucza API."}, status_code=400)
    if base_image is None:
        return JSONResponse({"error": "Brak zdjęcia bazowego."}, status_code=400)

    color_ids = [c.strip() for c in colors_csv.split(",") if c.strip()]
    if len(color_ids) < 2:
        return JSONResponse(
            {"error": "Wybierz co najmniej 2 kolory dla zestawu wariantów."},
            status_code=400,
        )
    if len(color_ids) > 8:
        return JSONResponse(
            {"error": "Limit zestawu to 8 kolorów na jeden run."},
            status_code=400,
        )

    try:
        base_path = await _save_upload(base_image)
    except Exception as exc:
        return JSONResponse({"error": f"Nie udało się odczytać obrazu: {exc}"}, status_code=400)

    # Optional user-supplied scene reference (independent of the auto-anchor flow).
    scene_path: Optional[Path] = None
    if scene_image is not None:
        try:
            scene_path = await _save_upload(scene_image, suffix="_scene")
        except Exception as exc:
            logger.warning("Scene reference image unreadable, ignoring: %s", exc)

    # ------------------------------------------------------------------ #
    # 1. Anchor render — first color in the list.
    # ------------------------------------------------------------------ #
    anchor_color = color_ids[0]
    logger.info("Variant set: anchor=%s, then %d more", anchor_color, len(color_ids) - 1)

    anchor_req = _build_generation_request(
        api_key=api_key, kind=kind,
        color=anchor_color, color_custom=color_custom,
        mat=mat, mat_notes=mat_notes,
        size=size, legs=legs, cam=cam,
        lens=lens, tod=tod, shadow=shadow,
        env=env, env_note=env_note, env_mode=env_mode,
        model=model, aspect=aspect, res=res, seed=seed,
        base_image_path=base_path,
        scene_image_path=scene_path,
    )

    anchor_result = await asyncio.to_thread(generate, anchor_req)

    if not anchor_result.success or anchor_result.output_path is None:
        return JSONResponse(
            {"error": f"Anchor render failed: {anchor_result.error_message or 'unknown'}"},
            status_code=500,
        )

    anchor_url = f"/api/outputs/{anchor_result.output_path.name}"
    anchor_payload = {
        "color": anchor_color,
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

    def _render_variant(color_id: str):
        # Build a request mirroring the anchor, then mutate color +
        # scene_reference_image + prior_history.
        v_req = _build_generation_request(
            api_key=api_key, kind=kind,
            color=color_id, color_custom=color_custom,
            mat=mat, mat_notes=mat_notes,
            size=size, legs=legs, cam=cam,
            lens=lens, tod=tod, shadow=shadow,
            env=env, env_note=env_note, env_mode=env_mode,
            model=model, aspect=aspect, res=res, seed=seed,
            base_image_path=base_path,
            scene_image_path=anchor_result.output_path,  # anchor PNG locks the scene
        )
        v_req = dataclass_replace(
            v_req,
            prior_history=list(anchor_history),
            turn_number=2,
        )
        return generate(v_req)

    variant_color_ids = color_ids[1:]
    variant_results = await asyncio.gather(
        *(asyncio.to_thread(_render_variant, cid) for cid in variant_color_ids),
        return_exceptions=True,
    )

    variants_payload = []
    for cid, r in zip(variant_color_ids, variant_results):
        if isinstance(r, Exception):
            variants_payload.append({"color": cid, "error": str(r)})
            continue
        if not r.success or r.output_path is None:
            variants_payload.append({"color": cid, "error": r.error_message or "unknown"})
            continue
        variants_payload.append({
            "color": cid,
            "image_url": f"/api/outputs/{r.output_path.name}",
            "generation_id": r.generation_id,
            "cost": r.actual_cost,
        })

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


@app.post("/api/generate-photoshoot")
async def api_generate_photoshoot(
    api_key: str = Form(""),
    kind: str = Form("sofa"),
    color: str = Form("saliw"),
    color_custom: str = Form(""),
    mat: str = Form("boucle"),
    mat_notes: str = Form(""),
    size: str = Form("3"),
    legs: str = Form("keep"),
    cam: str = Form("studio"),
    lens: str = Form("50mm_natural"),
    tod: str = Form("noon_neutral"),
    shadow: str = Form("soft_diffuse"),
    backdrop: str = Form("cyclorama_warm"),      # packshot env id (locked profile)
    lifestyle_env: str = Form("scandi"),         # lifestyle env id
    env_note: str = Form(""),
    model: str = Form("gemini-3.1-flash-image-preview"),
    aspect: str = Form("4:3"),
    res: str = Form("1K"),
    seed: str = Form(""),
    # Source images + per-source role flags. Lengths must match.
    # roles: "packshot" | "lifestyle" | "skip"
    sources: list[UploadFile] = File(...),
    source_roles_csv: str = Form(""),
):
    """
    Generate a full product photoshoot from user-supplied angle photos.

    Two passes:
      Pass A (packshot batch) — for each source tagged "packshot":
        - Render 1 (fabric anchor): full prompt on backdrop, no swatch.
        - Renders 2..N: anchor PNG as swatch_reference_image (slot 2)
          + use_swatch_for_fabric=True. Locks fabric color/texture exactly
          across the batch. Each call uses its own source image as base
          so the angle, frame geometry, and pose are preserved per shot.

      Pass B (lifestyle pair) — for each source tagged "lifestyle":
        - Render 1 (lifestyle anchor): full lifestyle prompt, establishes
          the room.
        - Render 2 (if present): anchor as scene_reference_image
          + view_consistency=True + prior_history=anchor.next_history.
          The room is locked; only the camera angle (from the second
          source's base image) changes.

    Returns:
      {
        "packshot": [ {label, image_url, anchor?, cost, ...}, ... ],
        "lifestyle": [ {label, image_url, anchor?, cost, ...}, ... ],
        "errors":   [ {label, role, error}, ... ],
        "total_cost": float,
      }
    """
    if not api_key.strip():
        return JSONResponse({"error": "Brak klucza API."}, status_code=400)

    if not sources:
        return JSONResponse({"error": "Brak zdjęć źródłowych."}, status_code=400)

    roles = [r.strip().lower() for r in source_roles_csv.split(",")]
    while len(roles) < len(sources):
        roles.append("packshot")   # default any unflagged source to packshot

    # Save all uploads to disk first; collect (path, role) tuples.
    saved: list[tuple[Path, str, str]] = []   # (path, role, original_filename)
    for upload, role in zip(sources, roles):
        if role == "skip":
            continue
        if role not in ("packshot", "lifestyle"):
            role = "packshot"
        try:
            p = await _save_upload(upload, suffix=f"_src_{role}")
            saved.append((p, role, upload.filename or ""))
        except Exception as exc:
            logger.warning("Skipping unreadable source %s: %s", upload.filename, exc)

    packshot_sources = [(p, fn) for (p, r, fn) in saved if r == "packshot"]
    lifestyle_sources = [(p, fn) for (p, r, fn) in saved if r == "lifestyle"]

    if not packshot_sources and not lifestyle_sources:
        return JSONResponse(
            {"error": "Brak czytelnych zdjęć źródłowych po dekodowaniu."},
            status_code=400,
        )
    if len(packshot_sources) + len(lifestyle_sources) > 10:
        return JSONResponse(
            {"error": "Limit sesji: max 10 zdjęć źródłowych (packshot + lifestyle)."},
            status_code=400,
        )

    logger.info(
        "Photoshoot: %d packshot + %d lifestyle sources",
        len(packshot_sources), len(lifestyle_sources),
    )

    # ------------------------------------------------------------------ #
    # Pass A — Packshot batch
    # ------------------------------------------------------------------ #
    packshot_results: list[dict] = []
    errors: list[dict] = []
    packshot_anchor_path: Optional[Path] = None
    # Look up the curated cyclorama reference once — used by both the anchor
    # and every variant so the backdrop look is locked pixel-level across
    # the whole batch.
    backdrop_ref_path = _scene_reference_path(backdrop)

    if packshot_sources:
        # 1. Anchor — first packshot source. The curated cyclorama reference
        # (if present) locks the backdrop look at pixel level.
        anchor_src_path, anchor_src_fn = packshot_sources[0]
        anchor_req = _build_generation_request(
            api_key=api_key, kind=kind,
            color=color, color_custom=color_custom,
            mat=mat, mat_notes=mat_notes,
            size=size, legs=legs, cam=cam,
            lens=lens, tod=tod, shadow=shadow,
            env=backdrop, env_note=env_note, env_mode="",
            model=model, aspect=aspect, res=res, seed=seed,
            base_image_path=anchor_src_path,
            scene_image_path=backdrop_ref_path,    # locks cyclorama look pixel-level
            preserve_camera_from_base=True,
        )
        if backdrop_ref_path:
            logger.info("Packshot anchor: using curated cyclorama reference %s", backdrop_ref_path.name)
        anchor_result = await asyncio.to_thread(generate, anchor_req)

        if not anchor_result.success or anchor_result.output_path is None:
            errors.append({
                "label": "v1",
                "source_filename": anchor_src_fn,
                "role": "packshot",
                "error": anchor_result.error_message or "anchor render failed",
            })
        else:
            packshot_anchor_path = anchor_result.output_path
            packshot_results.append({
                "label": "v1",
                "source_filename": anchor_src_fn,
                "image_url": f"/api/outputs/{anchor_result.output_path.name}",
                "anchor": True,
                "cost": anchor_result.actual_cost,
            })

        # 2. Remaining packshot variants — fan out in parallel.
        #
        # Earlier design used the anchor render as a fabric swatch reference
        # to lock cross-variant color consistency. That approach broke
        # framing fidelity: the model treated the anchor (a wide hero shot)
        # as a composition reference and collapsed every variant toward that
        # framing regardless of source angle — even with "slot 1 is framing
        # authority" repeated four times in the prompt. Visual references
        # outweigh text instructions in the model's attention.
        #
        # New design: variants render solo from their own source. The
        # backdrop is still locked via the curated cyclorama reference
        # (same as the anchor), which provides backdrop continuity without
        # leaking framing. Fabric/color consistency now comes from the
        # identical text prompt across variants (Gemini's color-name
        # interpretation is deterministic enough — drift is minimal vs.
        # the framing collapse the swatch caused).
        if packshot_anchor_path and len(packshot_sources) > 1:

            def _render_packshot_variant(idx: int, src_path: Path, src_fn: str):
                req = _build_generation_request(
                    api_key=api_key, kind=kind,
                    color=color, color_custom=color_custom,
                    mat=mat, mat_notes=mat_notes,
                    size=size, legs=legs, cam=cam,
                    lens=lens, tod=tod, shadow=shadow,
                    env=backdrop, env_note=env_note, env_mode="",
                    model=model, aspect=aspect, res=res, seed=seed,
                    base_image_path=src_path,
                    scene_image_path=backdrop_ref_path,  # same cyclorama lock as anchor
                    preserve_camera_from_base=True,
                )
                return idx, src_fn, generate(req)

            variant_jobs = [
                (i + 2, p, fn) for i, (p, fn) in enumerate(packshot_sources[1:])
            ]
            results = await asyncio.gather(
                *(asyncio.to_thread(_render_packshot_variant, idx, p, fn) for idx, p, fn in variant_jobs),
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception):
                    errors.append({"label": "v?", "role": "packshot", "error": str(r)})
                    continue
                idx, src_fn, gen_result = r
                if not gen_result.success or gen_result.output_path is None:
                    errors.append({
                        "label": f"v{idx}", "source_filename": src_fn,
                        "role": "packshot",
                        "error": gen_result.error_message or "render failed",
                    })
                    continue
                packshot_results.append({
                    "label": f"v{idx}",
                    "source_filename": src_fn,
                    "image_url": f"/api/outputs/{gen_result.output_path.name}",
                    "cost": gen_result.actual_cost,
                })
            packshot_results.sort(key=lambda x: int(x["label"][1:]))

    # ------------------------------------------------------------------ #
    # Pass B — Lifestyle pair (up to 2 shots sharing a room)
    # ------------------------------------------------------------------ #
    lifestyle_results: list[dict] = []
    if lifestyle_sources:
        # 1. Lifestyle anchor — establishes the room.
        anchor_src_path, anchor_src_fn = lifestyle_sources[0]
        # Labels continue from the packshot numbering so the user sees
        # a single coherent v1..vN sequence across the whole session.
        anchor_label = f"v{len(packshot_results) + len(errors) + 1}"
        anchor_req = _build_generation_request(
            api_key=api_key, kind=kind,
            color=color, color_custom=color_custom,
            mat=mat, mat_notes=mat_notes,
            size=size, legs=legs, cam=cam,
            lens=lens, tod=tod, shadow=shadow,
            env=lifestyle_env, env_note=env_note, env_mode="",
            model=model, aspect=aspect, res=res, seed=seed,
            base_image_path=anchor_src_path,
            scene_image_path=None,
            preserve_camera_from_base=True,
        )
        ls_anchor = await asyncio.to_thread(generate, anchor_req)

        if not ls_anchor.success or ls_anchor.output_path is None:
            errors.append({
                "label": anchor_label, "source_filename": anchor_src_fn,
                "role": "lifestyle",
                "error": ls_anchor.error_message or "lifestyle anchor failed",
            })
        else:
            lifestyle_results.append({
                "label": anchor_label,
                "source_filename": anchor_src_fn,
                "image_url": f"/api/outputs/{ls_anchor.output_path.name}",
                "anchor": True,
                "cost": ls_anchor.actual_cost,
            })

            # 2. Lifestyle variant 2 (if a second lifestyle source exists).
            if len(lifestyle_sources) >= 2:
                src2_path, src2_fn = lifestyle_sources[1]
                v2_label = f"v{len(packshot_results) + len(errors) + 2}"
                v2_req = _build_generation_request(
                    api_key=api_key, kind=kind,
                    color=color, color_custom=color_custom,
                    mat=mat, mat_notes=mat_notes,
                    size=size, legs=legs, cam=cam,
                    lens=lens, tod=tod, shadow=shadow,
                    env=lifestyle_env, env_note=env_note, env_mode="",
                    model=model, aspect=aspect, res=res, seed=seed,
                    base_image_path=src2_path,
                    scene_image_path=ls_anchor.output_path,
                    preserve_camera_from_base=True,
                )
                v2_req = dataclass_replace(
                    v2_req,
                    view_consistency=True,
                    prior_history=list(ls_anchor.next_history),
                    turn_number=2,
                )
                v2_result = await asyncio.to_thread(generate, v2_req)
                if not v2_result.success or v2_result.output_path is None:
                    errors.append({
                        "label": v2_label, "source_filename": src2_fn,
                        "role": "lifestyle",
                        "error": v2_result.error_message or "lifestyle v2 failed",
                    })
                else:
                    lifestyle_results.append({
                        "label": v2_label,
                        "source_filename": src2_fn,
                        "image_url": f"/api/outputs/{v2_result.output_path.name}",
                        "cost": v2_result.actual_cost,
                    })

    total_cost = (
        sum(p.get("cost", 0) for p in packshot_results)
        + sum(l.get("cost", 0) for l in lifestyle_results)
    )

    return {
        "success": True,
        "packshot": packshot_results,
        "lifestyle": lifestyle_results,
        "errors": errors,
        "total_cost": total_cost,
        "model": model,
        "backdrop": backdrop,
        "lifestyle_env": lifestyle_env,
    }


# Static files for the prototype JS / CSS — mounted last so dynamic routes win.
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")


def main() -> None:
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 7861))
    log_level = os.environ.get("LOG_LEVEL", "info")
    logger.info("Nano Sofa v2 starting on http://%s:%d  (outputs=%s)", host, port, _OUTPUT_DIR)
    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
