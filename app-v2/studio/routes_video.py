"""Video (Veo) — text-to-video, separate subpage from the sofa/bed image studio."""

from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.core.video_generator import (
    VideoRequest,
    generate_video,
    list_video_models,
)
from studio.errors import _validation_error
from studio.media import _prune_storage
from studio.paths import _DIST_DIR, _OUTPUT_DIR, logger

router = APIRouter()


@router.get("/video")
def video_page():
    return FileResponse(_DIST_DIR / "video.html")


@router.get("/api/video-models")
def api_video_models(api_key: str = ""):
    """
    Veo model catalog + per-model constraints for the video picker. When a key
    is supplied we probe the live API and keep only models that key can reach
    (falls back to the full catalog on any failure — the picker is never empty).
    """
    return list_video_models(api_key.strip())


@router.get("/api/video-diagnose")
def api_video_diagnose(api_key: str = ""):
    """
    Debug helper — what video models can this key actually see, and does a probe
    succeed? Helps answer "does my key have Veo access / is billing enabled".
    NOTE: models.list() usually lists models regardless of billing tier, so a
    visible Veo model does NOT guarantee generation works on a free tier.
    """
    from app.core.video_generator import VIDEO_MODELS  # noqa: PLC0415
    out: dict = {"probe_ok": False, "error": None, "total_models": 0,
                 "video_models_visible": [], "targets": {}}
    key = (api_key or "").strip()
    if not key:
        out["error"] = "Brak klucza."
        return out
    try:
        from google import genai
        from google.genai import types as gtypes
        client = genai.Client(api_key=key, http_options=gtypes.HttpOptions(timeout=30000))
        ids = []
        for m in client.models.list():
            nm = (getattr(m, "name", "") or "").split("/")[-1]
            if nm:
                ids.append(nm)
        out["probe_ok"] = True
        out["total_models"] = len(ids)
        low = lambda s: s.lower()
        out["video_models_visible"] = sorted(
            i for i in ids if any(k in low(i) for k in ("veo", "omni", "video"))
        )
        out["targets"] = {m["id"]: (m["id"] in ids) for m in VIDEO_MODELS}
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


@router.post("/api/generate-video")
async def api_generate_video(
    api_key: str = Form(""),
    prompt: str = Form(""),
    model: str = Form("veo-3.1-fast-generate-preview"),
    aspect: str = Form("16:9"),
    resolution: str = Form("720p"),
    duration: str = Form("8"),
    audio: str = Form("true"),
    negative_prompt: str = Form(""),
    seed: str = Form(""),
    image: Optional[UploadFile] = File(None),   # first-frame / reference (image-to-video)
):
    if not api_key.strip():
        return _validation_error("Brak klucza API.", "MISSING_API_KEY")
    if not prompt.strip():
        return _validation_error("Wpisz opis (prompt) filmu.", "INVALID_REQUEST")

    try:
        duration_i = int(str(duration).strip() or "8")
    except ValueError:
        duration_i = 8
    seed_i: Optional[int] = None
    if str(seed).strip():
        try:
            seed_i = int(str(seed).strip())
        except ValueError:
            seed_i = None

    # Optional starting-frame / reference image (image-to-video). Read the bytes
    # off the event loop and only pass real image data through.
    image_bytes: Optional[bytes] = None
    image_mime = "image/png"
    if image is not None and getattr(image, "filename", ""):
        raw = await image.read()
        if raw:
            ctype = (image.content_type or "").lower()
            if not ctype.startswith("image/"):
                return _validation_error(
                    "Klatka początkowa musi być obrazem (JPG / PNG / WebP).",
                    "INVALID_REQUEST",
                )
            image_bytes = raw
            image_mime = ctype or "image/png"

    req = VideoRequest(
        api_key=api_key.strip(),
        prompt=prompt.strip(),
        model_id=model.strip(),
        aspect_ratio=aspect.strip(),
        resolution=resolution.strip(),
        duration_seconds=duration_i,
        negative_prompt=negative_prompt.strip(),
        generate_audio=str(audio).strip().lower() in ("1", "true", "on", "yes"),
        seed=seed_i,
        image_bytes=image_bytes,
        image_mime=image_mime,
    )

    logger.info("Generating video: %s / %s / %ss", req.model_id, req.resolution, req.duration_seconds)
    result = await asyncio.to_thread(generate_video, req)

    if not result.success or not result.video_bytes:
        # error_detail carries the raw Gemini message — invaluable for telling a
        # bad param apart from a tier/access problem. Surfaced to the client.
        logger.warning("Video gen failed: %s | %s", result.error_code, result.error_detail)
        return JSONResponse(
            {
                "error": result.error_message or "Nie udało się wygenerować wideo.",
                "error_code": result.error_code or "UNKNOWN",
                "error_detail": result.error_detail or "",
                "retryable": result.retryable,
            },
            status_code=result.http_status or 500,
        )

    # Persist the mp4 alongside images so /api/outputs/{name} serves it and the
    # newest-N prune applies. The image history globs *.png, so videos don't
    # pollute it.
    short = req.model_id.replace("veo-", "").replace("-generate-preview", "").replace(".", "")
    name = f"video_{short}_{uuid.uuid4().hex[:8]}.mp4"
    out_path = _OUTPUT_DIR / name
    try:
        out_path.write_bytes(result.video_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to write video output: %s", exc)
        return JSONResponse(
            {"error": "Nie udało się zapisać pliku wideo na serwerze.",
             "error_code": "SERVER_MISCONFIG", "retryable": False},
            status_code=500,
        )
    await asyncio.to_thread(_prune_storage)

    return {
        "success": True,
        "video_url": f"/api/outputs/{name}",
        "mime_type": result.mime_type,
        "model": result.model_id,
        "resolution": result.resolution,
        "aspect": result.aspect_ratio,
        "duration": result.duration_seconds,
        "audio": result.audio,
        "engine": result.engine,
        "cost": result.estimated_cost_usd,
    }
