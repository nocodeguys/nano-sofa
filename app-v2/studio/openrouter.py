"""OpenRouter Images API path for the editorial tab.

The bake-off (docs/research/openrouter-vs-direct.md) showed FLUX/Seedream are
unusable for product-true edits — but the editorial tab is text-to-image from
scratch, exactly where they are strong. This module is that second engine:
same prompt text as the Gemini path, called through OpenRouter with the
user's own OpenRouter key (browser-stored, per request — mirroring the Gemini
key model; the server never persists it).

Since 2026-09 the same route also carries OpenAI's GPT Image models, which
accept up to 16 input references — the whole fabric reference set plus the
colour patch and the moodboards ride along as `input_references`.
"""

from __future__ import annotations

import base64
import io
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from PIL import Image

from app.core.cost_tracker import new_generation_id
from app.core.model_registry import registry
from studio.external_engine import (
    ALL_ASPECTS,
    ExternalEngineError,
    ReferenceItem,
    persist_external_render,
    reference_data_url,
)
from studio.openai_images import generate_product_external
from studio.paths import logger

# Editorial-only alternative models. Quirks (verified live against
# /api/v1/images/models/{slug}/endpoints, 2026-08 and 2026-09-08):
#  - openai/gpt-image-2 takes every aspect we offer, 0–16 input references
#    and a `quality` enum (low / medium / high); billed per token
#    (in 8 $/M image, 5 $/M text, out 30 $/M) so the hint is an estimate.
#  - openai/gpt-image-1 and -1-mini accept only 1:1 / 2:3 / 3:2.
#  - seedream-4.5 rejects resolution "1K" (enforces a ~3.7MP output minimum) —
#    we omit the resolution field everywhere and let provider defaults decide.
#  - flux.2-pro has no resolution parameter at all.
#  - krea-2-* supports a REDUCED aspect vocabulary (no 3:4, no 21:9) and only
#    ONE input reference; its pricing is not published in the endpoints API.
# `aspects` lists what the provider accepts from the page's vocabulary; the
# frontend disables the rest and _clamp_aspect is the server-side backstop.
# `qualities` (when present) is forwarded as the Images API `quality` field.
_ALL_ASPECTS = list(ALL_ASPECTS)


def _engine_cfg(m) -> dict:
    cfg = {
        "label": m.label,
        "max_refs": m.max_refs,
        "price_hint": m.pricing.get("price_hint", ""),
        "aspects": list(m.aspects) or list(_ALL_ASPECTS),
    }
    if m.qualities:
        cfg["qualities"] = list(m.qualities)
        cfg["default_quality"] = m.default_quality or m.qualities[-1]
    if m.resolutions and tuple(m.resolutions) != ("auto",):
        cfg["resolutions"] = list(m.resolutions)
    if m.product:
        cfg["product"] = True
    if m.note_pl:
        cfg["note_pl"] = m.note_pl
    return cfg


# slug → engine config view of the registry (OpenRouter models only; the
# per-model quirks above are encoded there as `aspects` / `qualities`).
OPENROUTER_MODELS = {m.id: _engine_cfg(m) for m in registry.by_engine("openrouter")}

# Nearest supported stand-ins for aspects a model lacks (same orientation).
# Followed as a chain until an allowed aspect is reached (21:9 → 16:9 → 3:2
# on the GPT Image 1 vocabulary).
_ASPECT_FALLBACK = {
    "3:4": "2:3", "4:3": "3:2", "21:9": "16:9", "16:9": "3:2", "9:16": "2:3",
    "4:5": "3:4", "9:21": "9:16",
}


def _clamp_aspect(model: str, aspect: str) -> str:
    allowed = OPENROUTER_MODELS.get(model, {}).get("aspects") or _ALL_ASPECTS
    if aspect in allowed:
        return aspect
    candidate, seen = aspect, set()
    while candidate not in allowed and candidate in _ASPECT_FALLBACK and candidate not in seen:
        seen.add(candidate)
        candidate = _ASPECT_FALLBACK[candidate]
    fallback = candidate if candidate in allowed else allowed[0]
    logger.warning("Aspect %s unsupported by %s — clamped to %s", aspect, model, fallback)
    return fallback


def _resolve_resolution(model: str, resolution: str) -> str:
    """The `resolution` value to send, or "" for models without the parameter
    (GPT Image via OpenRouter has no size parameter — provider default)."""
    resolutions = OPENROUTER_MODELS.get(model, {}).get("resolutions") or []
    if not resolutions:
        return ""
    res = (resolution or "").split(" ")[0].strip().upper()
    return res if res in resolutions else resolutions[0]


def _resolve_quality(model: str, quality: str) -> str:
    """The `quality` value to send, or "" for models without the parameter."""
    cfg = OPENROUTER_MODELS.get(model, {})
    qualities = cfg.get("qualities") or []
    if not qualities:
        return ""
    return quality if quality in qualities else cfg.get("default_quality", qualities[-1])


_API_URL = "https://openrouter.ai/api/v1/images"
_TIMEOUT_S = 300


class OpenRouterError(ExternalEngineError):
    pass


def _classify(status: int, body: str) -> OpenRouterError:
    if status in (401, 403):
        return OpenRouterError("Klucz OpenRouter jest nieprawidłowy lub wygasł.",
                               "INVALID_OPENROUTER_KEY", body, False, 401)
    if status == 402:
        return OpenRouterError("Brak środków na koncie OpenRouter — doładuj kredyty.",
                               "OPENROUTER_NO_CREDITS", body, False, 402)
    if status == 429:
        return OpenRouterError("Limit zapytań OpenRouter — spróbuj za chwilę.",
                               "RATE_LIMITED", body, True, 429)
    return OpenRouterError("Generowanie przez OpenRouter nie powiodło się.",
                           "OPENROUTER_ERROR", body, status >= 500, 502)


def generate_openrouter(
    *,
    api_key: str,
    model: str,
    prompt: str,
    aspect: str,
    references: Optional[list[ReferenceItem]] = None,
    quality: str = "",
    resolution: str = "",
    png_meta: Optional[dict[str, str]] = None,
    prompt_summary: str = "",
    trace_request: Any = None,
) -> dict:
    """Blocking call (run via asyncio.to_thread). Returns
    {generation_id, output_path, cost, elapsed_ms, model_id, resolution,
    quality} or raises OpenRouterError with a classified, user-facing
    message. `references` is the loaded freeform plan (role, source, image)."""
    t0 = time.monotonic()
    generation_id = new_generation_id()
    cfg = OPENROUTER_MODELS.get(model, {"max_refs": 4})

    refs = list(references or [])[: cfg["max_refs"]]

    payload: dict = {"model": model, "prompt": prompt,
                     "aspect_ratio": _clamp_aspect(model, aspect)}
    quality_used = _resolve_quality(model, quality)
    if quality_used:
        payload["quality"] = quality_used
    resolution_used = _resolve_resolution(model, resolution)
    if resolution_used:
        payload["resolution"] = resolution_used
    if refs:
        payload["input_references"] = [
            {"type": "image_url", "image_url": {"url": reference_data_url(source, image)}}
            for _role, source, image in refs
        ]

    logger.info("OpenRouter request: %s aspect=%s quality=%s res=%s refs=%d prompt=%d chars",
                model, payload["aspect_ratio"], quality_used or "-", resolution_used or "-",
                len(refs), len(prompt))
    try:
        r = httpx.post(
            _API_URL, json=payload, timeout=_TIMEOUT_S,
            headers={"Authorization": f"Bearer {api_key}", "X-Title": "nano-sofa editorial"},
        )
    except httpx.HTTPError as exc:
        raise OpenRouterError("Błąd sieci przy wywołaniu OpenRouter.",
                              "NETWORK_TIMEOUT", str(exc)[:300], True) from exc

    if r.status_code >= 400:
        logger.warning("OpenRouter %s failed: HTTP %s %s", model, r.status_code, r.text[:600])
        raise _classify(r.status_code, r.text[:300])

    try:
        data = r.json()
        img_b64 = data["data"][0]["b64_json"]
        image = Image.open(io.BytesIO(base64.b64decode(img_b64)))
        image.load()
    except Exception as exc:
        raise OpenRouterError("OpenRouter zwrócił nieczytelną odpowiedź.",
                              "OPENROUTER_ERROR", str(exc)[:300], True) from exc

    cost = float((data.get("usage") or {}).get("cost") or 0.0)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    output_path = persist_external_render(
        image=image,
        engine="openrouter",
        model=model,
        generation_id=generation_id,
        references=refs,
        cost=cost,
        elapsed_ms=elapsed_ms,
        resolution=resolution_used or "auto",
        prompt=prompt,
        prompt_summary=prompt_summary,
        png_meta={**(png_meta or {}), **({"nano_sofa_quality": quality_used} if quality_used else {})},
        trace_request=trace_request,
        extra_trace={"quality": quality_used} if quality_used else None,
    )
    logger.info("OpenRouter render OK: %s %.1fs $%.4f refs=%d quality=%s",
                model, elapsed_ms / 1000, cost, len(refs), quality_used or "-")
    return {
        "generation_id": generation_id,
        "output_path": output_path,
        "cost": cost,
        "elapsed_ms": elapsed_ms,
        "model_id": model,
        "resolution": resolution_used or "auto",
        "quality": quality_used,
    }


# Models the Lab product wizard may run through OpenRouter (registry `product`).
PRODUCT_MODELS = {slug: cfg for slug, cfg in OPENROUTER_MODELS.items() if cfg.get("product")}


def generate_product_openrouter(req: Any, api_key: str) -> Any:
    """The Lab product pipeline on OpenRouter — the same reference plan and
    prompt as the OpenAI-direct path (openai_images.generate_product_external),
    billed to the user's OpenRouter key."""
    cfg = OPENROUTER_MODELS.get(req.model_id, {"max_refs": 16})
    return generate_product_external(
        req, engine="openrouter", max_refs=cfg["max_refs"],
        render=lambda **kw: generate_openrouter(
            api_key=api_key, model=req.model_id, aspect=req.aspect_ratio,
            quality=req.engine_quality, resolution=req.resolution,
            trace_request=req, **kw,
        ),
    )
