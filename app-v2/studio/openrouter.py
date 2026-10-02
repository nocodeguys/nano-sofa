"""OpenRouter Images API path for the editorial tab.

The bake-off (docs/research/openrouter-vs-direct.md) showed FLUX/Seedream are
unusable for product-true edits — but the editorial tab is text-to-image from
scratch, exactly where they are strong. This module is that second engine:
same prompt text as the Gemini path, called through OpenRouter with the
user's own OpenRouter key (browser-stored, per request — mirroring the Gemini
key model; the server never persists it).

Since 2026-09 the same route also carries OpenAI's GPT Image models, which
accept up to 16 input references — the whole fabric reference set plus the
colour patch and the moodboards ride along as `input_references`. The models
flagged `product` also run the Lab tab's product wizard
(generate_product_openrouter): base photo + the full reference plan, the same
prompt the OpenAI-direct path sends, paid with the OpenRouter key.
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
from studio.external_engine import (
    ALL_ASPECTS,
    ExternalEngineError,
    ReferenceItem,
    persist_external_render,
    reference_data_url,
)
from studio.openai_images import generate_product_external
from studio.paths import logger

# Alternative models for the editorial tab; `product: True` ones are also
# offered in the Lab product wizard (edit-capable, product-true — the bake-off
# ruled FLUX / Seedream out of that pipeline). Quirks (verified live against
# /api/v1/images/models/{slug}/endpoints, 2026-08, 2026-09-08 and 2026-09-29):
#  - openai/gpt-image-2.5-flare / -sunburst: every aspect we offer, 0–16 input
#    references, quality low…max (adds xhigh / max), same token rates as
#    GPT Image 2. No size parameter — output size is the provider's default.
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
_GPT_IMAGE_QUALITIES = ["low", "medium", "high"]
_GPT_IMAGE_25_QUALITIES = ["low", "medium", "high", "xhigh", "max"]
OPENROUTER_MODELS = {
    "openai/gpt-image-2.5-flare": {
        "label": "GPT Image 2.5 Flare · OpenRouter",
        "max_refs": 16,
        "price_hint": "≈$0.01–0.13/obraz wg jakości",
        "aspects": _ALL_ASPECTS,
        "qualities": _GPT_IMAGE_25_QUALITIES,
        "default_quality": "high",
        "product": True,
        "note_pl": "ten sam model co Flare przez OpenAI, płatny kluczem OpenRouter",
    },
    "openai/gpt-image-2.5-sunburst": {
        "label": "GPT Image 2.5 Sunburst · OpenRouter",
        "max_refs": 16,
        "price_hint": "≈$0.01–0.13/obraz wg jakości",
        "aspects": _ALL_ASPECTS,
        "qualities": _GPT_IMAGE_25_QUALITIES,
        "default_quality": "high",
        "product": True,
        "note_pl": "ten sam model co Sunburst przez OpenAI, płatny kluczem OpenRouter",
    },
    "openai/gpt-image-2": {
        "label": "GPT Image 2 · OpenRouter",
        "max_refs": 16,
        "price_hint": "≈$0.01–0.13/obraz wg jakości",
        "aspects": _ALL_ASPECTS,
        "qualities": _GPT_IMAGE_QUALITIES,
        "default_quality": "high",
        "product": True,
    },
    "openai/gpt-image-1": {
        "label": "GPT Image 1 · OpenRouter",
        "max_refs": 16,
        "price_hint": "≈$0.01–0.17/obraz wg jakości",
        "aspects": ["1:1", "2:3", "3:2"],
        "qualities": _GPT_IMAGE_QUALITIES,
        "default_quality": "medium",
    },
    "openai/gpt-image-1-mini": {
        "label": "GPT Image 1 mini · OpenRouter",
        "max_refs": 16,
        "price_hint": "≈$0.002–0.04/obraz wg jakości",
        "aspects": ["1:1", "2:3", "3:2"],
        "qualities": _GPT_IMAGE_QUALITIES,
        "default_quality": "medium",
    },
    "black-forest-labs/flux.2-pro": {
        "label": "FLUX.2 pro · OpenRouter",
        "max_refs": 8,
        "price_hint": "~$0.06/obraz",
        "aspects": _ALL_ASPECTS,
    },
    "bytedance-seed/seedream-4.5": {
        "label": "Seedream 4.5 · OpenRouter",
        "max_refs": 14,
        "price_hint": "$0.04/obraz",
        "aspects": _ALL_ASPECTS,
    },
    "bytedance-seed/seedream-5-0-pro": {
        "label": "Seedream 5.0 Pro · OpenRouter",
        "max_refs": 14,
        "price_hint": "$0.045/obraz",
        "aspects": _ALL_ASPECTS,
    },
    "bytedance-seed/seedream-5-0-lite": {
        "label": "Seedream 5.0 Lite · OpenRouter",
        "max_refs": 14,
        "price_hint": "$0.035/obraz",
        "aspects": _ALL_ASPECTS,
    },
    "krea/krea-2-large": {
        "label": "Krea 2 Large · OpenRouter",
        "max_refs": 1,
        "price_hint": "cena wg OpenRouter",
        "aspects": ["1:1", "4:3", "2:3", "3:2", "9:16", "16:9"],
    },
    "krea/krea-2-medium": {
        "label": "Krea 2 Medium · OpenRouter",
        "max_refs": 1,
        "price_hint": "cena wg OpenRouter",
        "aspects": ["1:1", "4:3", "2:3", "3:2", "9:16", "16:9"],
    },
}

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


def _legacy_references(ref_paths: list[Path]) -> list[ReferenceItem]:
    items: list[ReferenceItem] = []
    for index, path in enumerate(ref_paths, start=1):
        try:
            image = Image.open(str(path))
            image.load()
        except Exception as exc:
            logger.warning("OpenRouter reference %s unreadable, skipping: %s", path, exc)
            continue
        items.append((f"extra_reference_{index}", path, image))
    return items


def generate_openrouter(
    *,
    api_key: str,
    model: str,
    prompt: str,
    aspect: str,
    references: Optional[list[ReferenceItem]] = None,
    ref_paths: Optional[list[Path]] = None,
    quality: str = "",
    png_meta: Optional[dict[str, str]] = None,
    prompt_summary: str = "",
    trace_request: Any = None,
) -> dict:
    """Blocking call (run via asyncio.to_thread). Returns
    {generation_id, output_path, cost, elapsed_ms, model_id, resolution,
    quality} or raises OpenRouterError with a classified, user-facing
    message. `references` is the loaded freeform plan (role, source, image);
    `ref_paths` is the pre-plan calling convention kept for scripts."""
    t0 = time.monotonic()
    generation_id = new_generation_id()
    cfg = OPENROUTER_MODELS.get(model, {"max_refs": 4})

    refs = list(references or [])
    if not refs and ref_paths:
        refs = _legacy_references(list(ref_paths))
    refs = refs[: cfg["max_refs"]]

    payload: dict = {"model": model, "prompt": prompt,
                     "aspect_ratio": _clamp_aspect(model, aspect)}
    quality_used = _resolve_quality(model, quality)
    if quality_used:
        payload["quality"] = quality_used
    if refs:
        payload["input_references"] = [
            {"type": "image_url", "image_url": {"url": reference_data_url(source, image)}}
            for _role, source, image in refs
        ]

    logger.info("OpenRouter request: %s aspect=%s quality=%s refs=%d prompt=%d chars",
                model, payload["aspect_ratio"], quality_used or "-", len(refs), len(prompt))
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
        resolution="auto",
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
        "resolution": "auto",
        "quality": quality_used,
    }


# Models the Lab product wizard may run through OpenRouter.
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
            quality=req.engine_quality, trace_request=req, **kw,
        ),
    )
