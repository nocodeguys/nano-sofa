"""OpenRouter Images API path for the editorial tab.

The bake-off (docs/research/openrouter-vs-direct.md) showed FLUX/Seedream are
unusable for product-true edits — but the editorial tab is text-to-image from
scratch, exactly where they are strong. This module is that second engine:
same prompt text as the Gemini path, called through OpenRouter with the
user's own OpenRouter key (browser-stored, per request — mirroring the Gemini
key model; the server never persists it).
"""

from __future__ import annotations

import base64
import io
import time
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image

from app.core.cost_tracker import new_generation_id
from studio.paths import _OUTPUT_DIR, logger

# Editorial-only alternative models. Quirks (verified live against
# /api/v1/images/models/{slug}/endpoints, 2026-08):
#  - seedream-4.5 rejects resolution "1K" (enforces a ~3.7MP output minimum) —
#    we omit the resolution field everywhere and let provider defaults decide.
#  - flux.2-pro has no resolution parameter at all.
#  - krea-2-* supports a REDUCED aspect vocabulary (no 3:4, no 21:9) and only
#    ONE input reference; its pricing is not published in the endpoints API.
# `aspects` lists what the provider accepts from the page's vocabulary; the
# frontend disables the rest and _clamp_aspect is the server-side backstop.
_ALL_ASPECTS = ["1:1", "3:4", "4:3", "2:3", "3:2", "9:16", "16:9", "21:9"]
OPENROUTER_MODELS = {
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
_ASPECT_FALLBACK = {"3:4": "2:3", "21:9": "16:9", "4:5": "3:4", "9:21": "9:16"}


def _clamp_aspect(model: str, aspect: str) -> str:
    allowed = OPENROUTER_MODELS.get(model, {}).get("aspects") or _ALL_ASPECTS
    if aspect in allowed:
        return aspect
    fallback = _ASPECT_FALLBACK.get(aspect, allowed[0])
    fallback = fallback if fallback in allowed else allowed[0]
    logger.warning("Aspect %s unsupported by %s — clamped to %s", aspect, model, fallback)
    return fallback

_API_URL = "https://openrouter.ai/api/v1/images"
_TIMEOUT_S = 300


class OpenRouterError(Exception):
    def __init__(self, message_pl: str, code: str, detail: str = "", retryable: bool = False,
                 http_status: int = 502):
        super().__init__(message_pl)
        self.message_pl = message_pl
        self.code = code
        self.detail = detail
        self.retryable = retryable
        self.http_status = http_status


def _data_url(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".") or "png"
    mime = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix}"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


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
    ref_paths: Optional[list[Path]] = None,
) -> dict:
    """Blocking call (run via asyncio.to_thread). Returns
    {generation_id, output_path, cost, elapsed_ms, model_id} or raises
    OpenRouterError with a classified, user-facing message."""
    t0 = time.monotonic()
    generation_id = new_generation_id()
    cfg = OPENROUTER_MODELS.get(model, {"max_refs": 4})

    payload: dict = {"model": model, "prompt": prompt,
                     "aspect_ratio": _clamp_aspect(model, aspect)}
    refs = list(ref_paths or [])[: cfg["max_refs"]]
    if refs:
        payload["input_references"] = [
            {"type": "image_url", "image_url": {"url": _data_url(p)}} for p in refs
        ]

    try:
        r = httpx.post(
            _API_URL, json=payload, timeout=_TIMEOUT_S,
            headers={"Authorization": f"Bearer {api_key}", "X-Title": "nano-sofa editorial"},
        )
    except httpx.HTTPError as exc:
        raise OpenRouterError("Błąd sieci przy wywołaniu OpenRouter.",
                              "NETWORK_TIMEOUT", str(exc)[:300], True) from exc

    if r.status_code >= 400:
        raise _classify(r.status_code, r.text[:300])

    try:
        data = r.json()
        img_b64 = data["data"][0]["b64_json"]
        image = Image.open(io.BytesIO(base64.b64decode(img_b64)))
        image.load()
    except Exception as exc:
        raise OpenRouterError("OpenRouter zwrócił nieczytelną odpowiedź.",
                              "OPENROUTER_ERROR", str(exc)[:300], True) from exc

    # Persist the lossless PNG master using the same naming scheme as the
    # Gemini path, so /api/outputs, gallery and retention treat both alike.
    ts = int(time.time())
    safe_model = model.replace("/", "-").replace(".", "-")
    output_path = _OUTPUT_DIR / f"{ts}_{safe_model}_{generation_id[:8]}.png"
    image.save(output_path, format="PNG", optimize=True)

    cost = float((data.get("usage") or {}).get("cost") or 0.0)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info("OpenRouter render OK: %s %.1fs $%.4f", model, elapsed_ms / 1000, cost)
    return {
        "generation_id": generation_id,
        "output_path": output_path,
        "cost": cost,
        "elapsed_ms": elapsed_ms,
        "model_id": model,
    }
