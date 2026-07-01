"""
Text-to-video generation via Google Veo (Gemini Developer API), google-genai 2.0.0.

Standalone from generator.py (which is image-only) but reuses its error taxonomy
(classify_exception) so the frontend renders video failures with the same typed
error cards. Bring-your-own-key, same trust model as the image pipeline: the key
is passed per request and never persisted server-side.

The Veo flow is a long-running operation:
    op = client.models.generate_videos(model, prompt, config)   # returns immediately
    while not op.done: op = client.operations.get(op)           # poll
    video = op.response.generated_videos[0].video               # mp4 bytes / uri

Model catalog + per-model constraints live in VIDEO_MODELS below. The catalog is
the source of truth for the picker; list_video_models() optionally intersects it
with a live client.models.list() probe so the UI only offers models the user's
key can actually reach (honours "check via the API which models are available"),
degrading to the full catalog if the probe fails.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

from app.core.generator import classify_exception  # shared error taxonomy

logger = logging.getLogger("nano-sofa-video")

# Per-HTTP-call timeout (ms). generate_videos + each poll is a short call; the
# long wait happens across many polls, bounded by _MAX_WAIT_S below.
_REQUEST_TIMEOUT_MS = int(os.environ.get("GEMINI_TIMEOUT_MS", "120000"))
# Seconds between long-running-operation polls, and the overall wall-clock
# budget for one video (Veo clips typically finish in 1–3 min).
_POLL_INTERVAL_S = float(os.environ.get("VEO_POLL_INTERVAL_S", "10"))
_MAX_WAIT_S = float(os.environ.get("VEO_MAX_WAIT_S", "600"))


# ---------------------------------------------------------------------------
# Model catalog — Gemini Developer API (api_key auth, NOT Vertex).
# Verified 2026-07-01 against ai.google.dev (models / video guide / pricing /
# deprecations). Only the Veo 3.1 family is live for new text-to-video; Veo 2 /
# Veo 3.0 are deprecated (shutdown 2026-06-30) and deliberately excluded.
#
#   price_per_second_usd  → base 720p rate, USD/s (shown in the "$X/s" label)
#   price_by_resolution   → exact USD/s per resolution (used for cost estimate)
#   audio                 → native audio is ALWAYS ON for 3.1 (price includes it,
#                           it is not a toggle) — flag is informational only.
#
# Constraints (see _HD_* below): 1080p and 4k each require duration_seconds=8
# and 16:9 (portrait 9:16 is 720p-only). number_of_videos is FIXED at 1.
# ---------------------------------------------------------------------------
VIDEO_MODELS: list[dict[str, Any]] = [
    {
        "id": "veo-3.1-generate-preview",
        "label": "Veo 3.1",
        "tier": "standard",
        "price_per_second_usd": 0.40,
        "price_by_resolution": {"720p": 0.40, "1080p": 0.40, "4k": 0.60},
        "resolutions": ["720p", "1080p", "4k"],
        "aspect_ratios": ["16:9", "9:16"],
        "durations_seconds": [4, 6, 8],
        "audio": True,
        "notes": "Najwyższa jakość, natywny dźwięk, złożone ruchy kamery. Do 4K.",
    },
    {
        "id": "veo-3.1-fast-generate-preview",
        "label": "Veo 3.1 Fast",
        "tier": "fast",
        "price_per_second_usd": 0.10,
        "price_by_resolution": {"720p": 0.10, "1080p": 0.12, "4k": 0.30},
        "resolutions": ["720p", "1080p", "4k"],
        "aspect_ratios": ["16:9", "9:16"],
        "durations_seconds": [4, 6, 8],
        "audio": True,
        "notes": "Szybszy i tańszy, z dźwiękiem. Dobry do iteracji. Do 4K.",
    },
    {
        "id": "veo-3.1-lite-generate-preview",
        "label": "Veo 3.1 Lite",
        "tier": "lite",
        "price_per_second_usd": 0.05,
        "price_by_resolution": {"720p": 0.05, "1080p": 0.08},
        "resolutions": ["720p", "1080p"],
        "aspect_ratios": ["16:9", "9:16"],
        "durations_seconds": [4, 6, 8],
        "audio": True,
        "notes": "Najtańszy, do dużej ilości materiału. Bez 4K.",
    },
]

# 1080p and 4k are only produced at 16:9 / 8 s (portrait 9:16 is 720p-only).
# Enforced server-side in _validate() and mirrored in the UI so the user can't
# build an invalid combination.
_HD_RESOLUTIONS = {"1080p", "4k"}
_HD_ASPECT = "16:9"
_HD_DURATION = 8

_MODELS_BY_ID = {m["id"]: m for m in VIDEO_MODELS}
_DEFAULT_MODEL = "veo-3.1-fast-generate-preview"


def catalog() -> dict[str, Any]:
    """The static catalog payload (used as the /api/video-models fallback)."""
    return {
        "models": VIDEO_MODELS,
        "default_model": _DEFAULT_MODEL if _DEFAULT_MODEL in _MODELS_BY_ID else (
            VIDEO_MODELS[0]["id"] if VIDEO_MODELS else None
        ),
        # Resolutions that force 16:9 + 8 s. The UI reads this to disable invalid
        # aspect/duration combinations.
        "hd": {
            "resolutions": sorted(_HD_RESOLUTIONS),
            "aspect_ratio": _HD_ASPECT,
            "duration_seconds": _HD_DURATION,
        },
    }


def list_video_models(api_key: str = "") -> dict[str, Any]:
    """
    Return the catalog, optionally filtered to models the given key can reach.

    Probes client.models.list() and keeps only curated models whose id the API
    reports as available. Any failure (bad key, offline, SDK missing, empty
    result) falls back to the full curated catalog so the picker is never empty.
    """
    base = catalog()
    key = (api_key or "").strip() or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return base
    try:
        from google import genai
        from google.genai import types as gtypes

        client = genai.Client(
            api_key=key,
            http_options=gtypes.HttpOptions(timeout=_REQUEST_TIMEOUT_MS),
        )
        available: set[str] = set()
        for m in client.models.list():
            name = (getattr(m, "name", "") or "").split("/")[-1]
            if name:
                available.add(name)
        if not available:
            return base
        # Keep curated order; match by exact id, tolerating a "models/" prefix.
        filtered = [m for m in VIDEO_MODELS if m["id"] in available]
        if not filtered:
            # The account has models but none of our curated ids surfaced (e.g.
            # list() doesn't enumerate preview video models). Don't hide the tab.
            return base
        default = _DEFAULT_MODEL if any(m["id"] == _DEFAULT_MODEL for m in filtered) else filtered[0]["id"]
        return {**base, "models": filtered, "default_model": default}
    except Exception as exc:  # noqa: BLE001 — never let a probe break the picker
        logger.info("Video model probe failed, using static catalog: %s", exc)
        return base


@dataclass
class VideoRequest:
    api_key: str
    prompt: str
    model_id: str = _DEFAULT_MODEL
    aspect_ratio: str = "16:9"
    resolution: str = "720p"
    duration_seconds: int = 8
    negative_prompt: str = ""
    # Native audio is always on for Veo 3.1 (kept for forward-compat / API req).
    generate_audio: bool = True
    # "allow_adult" is the Gemini API default and the only value accepted in
    # EU/UK/CH/MENA — safe everywhere (allows adult humans, blocks minors).
    # "allow_all" would be rejected in those regions, so we don't default to it.
    person_generation: str = "allow_adult"
    seed: Optional[int] = None


@dataclass
class VideoResult:
    success: bool
    video_bytes: Optional[bytes] = None
    mime_type: str = "video/mp4"
    model_id: str = ""
    prompt: str = ""
    duration_seconds: int = 0
    resolution: str = ""
    aspect_ratio: str = ""
    audio: bool = False
    estimated_cost_usd: float = 0.0
    error_message: str = ""
    error_code: str = ""
    error_detail: str = ""
    retryable: bool = False
    http_status: int = 200


def estimate_cost(model_id: str, resolution: str, duration_seconds: int) -> float:
    m = _MODELS_BY_ID.get(model_id)
    if not m:
        return 0.0
    per_res = m.get("price_by_resolution") or {}
    rate = per_res.get(resolution, m["price_per_second_usd"])
    return round(float(rate) * max(0, int(duration_seconds)), 2)


def _validate(req: VideoRequest) -> Optional[VideoResult]:
    """Cheap, deterministic input validation → typed error, or None if OK."""
    def bad(msg_pl: str, detail: str) -> VideoResult:
        return VideoResult(
            success=False, model_id=req.model_id, prompt=req.prompt,
            error_message=msg_pl, error_code="INVALID_REQUEST",
            error_detail=detail, retryable=False, http_status=400,
        )

    if not (req.api_key or "").strip() and not os.environ.get("GEMINI_API_KEY"):
        return VideoResult(
            success=False, model_id=req.model_id, prompt=req.prompt,
            error_message="Brak klucza API. Wklej swój klucz Gemini API u góry.",
            error_code="MISSING_API_KEY", retryable=False, http_status=400,
        )
    if not (req.prompt or "").strip():
        return bad("Wpisz opis (prompt) filmu.", "empty prompt")
    m = _MODELS_BY_ID.get(req.model_id)
    if not m:
        return bad(f"Nieznany model wideo: {req.model_id}.", "unknown model id")
    if req.resolution not in m["resolutions"]:
        return bad(
            f"Model {m['label']} nie obsługuje rozdzielczości {req.resolution}.",
            "resolution not supported by model",
        )
    if req.aspect_ratio not in m["aspect_ratios"]:
        return bad(
            f"Model {m['label']} nie obsługuje proporcji {req.aspect_ratio}.",
            "aspect ratio not supported by model",
        )
    if req.duration_seconds not in m["durations_seconds"]:
        allowed = ", ".join(f"{d}s" for d in m["durations_seconds"])
        return bad(
            f"Dozwolona długość dla {m['label']}: {allowed}.",
            "duration not supported by model",
        )
    if req.resolution in _HD_RESOLUTIONS:
        if req.aspect_ratio != _HD_ASPECT:
            return bad(f"{req.resolution} jest dostępne tylko dla proporcji 16:9.",
                       f"{req.resolution} requires 16:9")
        if req.duration_seconds != _HD_DURATION:
            return bad(f"{req.resolution} jest dostępne tylko dla długości 8 s.",
                       f"{req.resolution} requires 8s")
    return None


def _operation_error(op: Any) -> Optional[VideoResult]:
    """Map a failed long-running operation's error into a typed VideoResult."""
    err = getattr(op, "error", None)
    if not err:
        return None
    # op.error is a google.rpc.Status-like: {code, message}. gRPC codes differ
    # from HTTP; surface the message and treat it as retryable upstream trouble.
    msg = ""
    try:
        msg = err.get("message") if isinstance(err, dict) else getattr(err, "message", "")
    except Exception:  # noqa: BLE001
        msg = str(err)
    return VideoResult(
        success=False,
        error_message="Błąd generowania wideo po stronie Gemini. Spróbuj ponownie.",
        error_code="UPSTREAM_ERROR",
        error_detail=str(msg) or str(err),
        retryable=True,
        http_status=502,
    )


def generate_video(req: VideoRequest) -> VideoResult:
    """
    Generate one video with Veo and return its raw mp4 bytes. Synchronous /
    blocking (polls in a loop) — call it via asyncio.to_thread from the server
    so it never freezes the event loop.
    """
    invalid = _validate(req)
    if invalid is not None:
        return invalid

    api_key = (req.api_key or "").strip() or os.environ.get("GEMINI_API_KEY", "")
    model = _MODELS_BY_ID[req.model_id]

    try:
        from google import genai
        from google.genai import types as gtypes
    except ImportError:
        return VideoResult(
            success=False, model_id=req.model_id, prompt=req.prompt,
            error_message="Błąd konfiguracji serwera. Skontaktuj się z administratorem.",
            error_code="SERVER_MISCONFIG",
            error_detail="google-genai package not installed.",
            retryable=False, http_status=500,
        )

    client = genai.Client(
        api_key=api_key,
        http_options=gtypes.HttpOptions(timeout=_REQUEST_TIMEOUT_MS),
    )

    cfg_kwargs: dict[str, Any] = {
        "aspect_ratio": req.aspect_ratio,
        "resolution": req.resolution,
        "duration_seconds": int(req.duration_seconds),
        "number_of_videos": 1,  # fixed at 1 for the Veo 3.1 family
        "person_generation": req.person_generation,
    }
    if req.negative_prompt.strip():
        cfg_kwargs["negative_prompt"] = req.negative_prompt.strip()
    if req.seed is not None:
        cfg_kwargs["seed"] = int(req.seed)

    try:
        config = gtypes.GenerateVideosConfig(**cfg_kwargs)
        logger.info("Veo generate_videos model=%s res=%s aspect=%s dur=%ss",
                    req.model_id, req.resolution, req.aspect_ratio, req.duration_seconds)
        operation = client.models.generate_videos(
            model=req.model_id,
            prompt=req.prompt.strip(),
            config=config,
        )

        waited = 0.0
        while not operation.done:
            if waited >= _MAX_WAIT_S:
                return VideoResult(
                    success=False, model_id=req.model_id, prompt=req.prompt,
                    error_message=("Generowanie wideo trwało zbyt długo i zostało "
                                   "przerwane. Spróbuj ponownie."),
                    error_code="NETWORK_TIMEOUT", retryable=True, http_status=504,
                )
            time.sleep(_POLL_INTERVAL_S)
            waited += _POLL_INTERVAL_S
            operation = client.operations.get(operation)

        op_err = _operation_error(operation)
        if op_err is not None:
            op_err.model_id, op_err.prompt = req.model_id, req.prompt
            return op_err

        response = getattr(operation, "response", None)
        videos = getattr(response, "generated_videos", None) if response else None
        if not videos:
            # No video came back — almost always a safety / policy filter.
            return VideoResult(
                success=False, model_id=req.model_id, prompt=req.prompt,
                error_message=("Model nie zwrócił wideo — prawdopodobnie blokada "
                               "bezpieczeństwa treści. Zmień prompt i spróbuj ponownie."),
                error_code="SAFETY_NO_IMAGE", retryable=False, http_status=422,
            )

        video = videos[0].video
        data = getattr(video, "video_bytes", None)
        if not data:
            # On the Developer API the video is a Files-API reference: bytes are
            # empty until downloaded. download() returns the bytes AND fills
            # video.video_bytes in place — tolerate either shape.
            downloaded = client.files.download(file=video)
            data = downloaded or getattr(video, "video_bytes", None)
        if not data:
            return VideoResult(
                success=False, model_id=req.model_id, prompt=req.prompt,
                error_message=("Wideo zostało wygenerowane, ale nie udało się pobrać "
                               "pliku. Spróbuj ponownie."),
                error_code="UPSTREAM_ERROR", retryable=True, http_status=502,
            )
        mime = getattr(video, "mime_type", None) or "video/mp4"

        return VideoResult(
            success=True,
            video_bytes=data,
            mime_type=mime,
            model_id=req.model_id,
            prompt=req.prompt,
            duration_seconds=int(req.duration_seconds),
            resolution=req.resolution,
            aspect_ratio=req.aspect_ratio,
            audio=bool(model["audio"]),
            estimated_cost_usd=estimate_cost(req.model_id, req.resolution, req.duration_seconds),
        )
    except Exception as exc:  # noqa: BLE001
        info = classify_exception(exc)
        logger.warning("Veo generation failed: %s (%s)", info.error_code, exc)
        return VideoResult(
            success=False, model_id=req.model_id, prompt=req.prompt,
            error_message=info.message_pl, error_code=info.error_code,
            error_detail=str(exc), retryable=info.retryable,
            http_status=info.http_status,
        )
