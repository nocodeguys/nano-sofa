"""
server.py — FastAPI backend for Nano Sofa Studio v2.

Serves the static React/HTML/CSS prototype from ./static and exposes:
  GET  /                   → Nano Sofa Studio.html
  GET  /<asset>            → other prototype assets (jsx, css)
  POST /api/generate       → run a single generation
  GET  /api/outputs/<file> → serve a generated image

Wraps app/core/generator.py from the parent project (shared with v1).
Run with:
    cd <repo-root> && python app-v2/server.py
"""

from __future__ import annotations

import io
import logging
import sys
import uuid
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

# Environment id (from data.jsx ENVIRONMENTS) → scene description fed to the prompt.
_ENV_TO_SCENE = {
    "studio_white":  "clean white studio cyclorama, soft even lighting, e-commerce catalog",
    "studio_grey":   "neutral grey studio cyclorama, packshot lighting",
    "scandi":        "scandinavian living room with light oak floors, white walls, indoor plants",
    "loft":          "industrial loft with exposed brick, concrete, and dark metal accents",
    "japandi":       "japandi interior, warm minimalist palette, natural wood, soft light",
    "boho":          "bohemian living room with rattan, woven textiles, warm earthy tones",
    "dark_moody":    "moody dark interior with deep walls and warm lamp lighting",
    "garden":        "outdoor terrace / garden setting with greenery and natural daylight",
    "showroom":      "brand showroom with subtle product staging, neutral palette",
    "transparent":   "transparent background, isolated product, no environment, alpha PNG output",
    "custom":        "custom interior referenced by the user's uploaded background image",
}

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Nano Sofa Studio v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_STATIC_DIR = _THIS  # serve prototype files from app-v2/
_UPLOAD_DIR = _REPO_ROOT / "outputs" / "v2-uploads"
_OUTPUT_DIR = _REPO_ROOT / "outputs"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/")
def index():
    return FileResponse(_STATIC_DIR / "Nano Sofa Studio v2.html")


@app.get("/v1")
def index_v1():
    return FileResponse(_STATIC_DIR / "Nano Sofa Studio.html")


@app.get("/api/outputs/{name}")
def get_output(name: str):
    candidate = _OUTPUT_DIR / name
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(candidate)


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
    lens: str = Form("50 mm — naturalna"),
    tod: str = Form("południe — neutralne"),
    shadow: str = Form("miękkie rozproszone"),
    env: str = Form(""),
    env_note: str = Form(""),
    env_mode: str = Form(""),
    model: str = Form("gemini-2.5-flash-image"),
    aspect: str = Form("4:3"),
    res: str = Form("1K — Flash limit"),
    seed: str = Form(""),
    base_image: Optional[UploadFile] = File(None),
):
    if not api_key.strip():
        return JSONResponse({"error": "Brak klucza API."}, status_code=400)
    if base_image is None:
        return JSONResponse({"error": "Brak zdjęcia bazowego."}, status_code=400)

    raw = await base_image.read()
    try:
        pil = Image.open(io.BytesIO(raw))
        pil.load()
    except Exception as exc:
        return JSONResponse({"error": f"Nie udało się odczytać obrazu: {exc}"}, status_code=400)

    upload_path = _UPLOAD_DIR / f"{uuid.uuid4().hex}.png"
    pil.convert("RGB").save(upload_path, format="PNG")

    upholstery_color = color_custom.strip() if color == "custom" and color_custom.strip() \
        else _COLOR_PL_TO_EN.get(color, "neutral")
    upholstery_material = _MATERIAL_PL_TO_EN.get(mat, "fabric")

    is_bed = kind == "bed"
    sofa_config = (_BED_CONFIG if is_bed else _SOFA_CONFIG).get(size, "3-seater")

    camera_angle, deg = _CAMERA_TO_ANGLE.get(cam, ("front-34-left", 35))

    try:
        focal_length_mm = int(lens.split(" mm")[0].strip())
    except Exception:
        focal_length_mm = 50

    shadow_map = {
        "miękkie rozproszone": "soft diffuse, no strong directional shadow",
        "kierunkowe — okno": "4 o-clock",
        "twarde — studio": "5 o-clock hard",
    }
    shadow_direction = shadow_map.get(shadow, "soft diffuse, no strong directional shadow")

    resolution = "2K" if res.startswith("2K") else "1K"

    leg_count = 0 if is_bed and legs == "keep" else 4
    leg_id = _LEG_TO_ID.get(legs)

    notes_parts = []
    if tod:
        notes_parts.append(f"time of day: {tod}")
    env_scene = _ENV_TO_SCENE.get(env, "")
    if env_scene:
        notes_parts.append(f"environment: {env_scene}")
    if env_note.strip():
        notes_parts.append(f"environment note: {env_note.strip()}")
    if env_mode.strip():
        notes_parts.append(f"environment use: {env_mode.strip()}")
    if seed.strip():
        notes_parts.append(f"seed hint: {seed.strip()}")

    req = GenerationRequest(
        model_id=model,
        base_product_image=str(upload_path),
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
        shadow_direction=shadow_direction,
        focal_length_mm=focal_length_mm,
        aspect_ratio=aspect,
        resolution=resolution,
        notes=" | ".join(notes_parts),
        api_key=api_key.strip(),
    )

    logger.info("Generating: %s / %s / %s", upholstery_color, upholstery_material, camera_angle)
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


# Static files for the prototype JS / CSS — mounted last so dynamic routes win.
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")


def main() -> None:
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 7861))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
