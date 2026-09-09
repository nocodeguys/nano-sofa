"""OpenAI Images API path — the experimental Lab tab (/lab).

GPT Image 2.5 Flare / Sunburst (released 2026-09-08) are called directly at
api.openai.com with the user's own OpenAI key (browser-stored, forwarded per
request, never persisted — the same model as the Gemini and OpenRouter keys).

The prompt is the very same composed editorial prompt as the Gemini and
OpenRouter engines get. When references are attached (fabric macro, exact
colour patch, oblique / behaviour / application views, moodboards — up to
16) the call goes to /v1/images/edits with `input_fidelity: high`; without
references it is a plain /v1/images/generations call. Sizes are explicit
WIDTHxHEIGHT (multiples of 16, see external_engine.size_for_aspect) and cost
is computed from the returned token usage at the model's published rates.
"""

from __future__ import annotations

import base64
import io
import json
import time
from typing import Any, Optional

import httpx
from PIL import Image

from app.core.cost_tracker import new_generation_id
from app.core.generator import (
    GenerationRequest,
    GenerationResult,
    _build_prompt_text,
    _flatten_alpha,
    _load_image,
    _load_reference_plan,
    slot_numbers,
)
from studio.external_engine import (
    ALL_ASPECTS,
    ExternalEngineError,
    ReferenceItem,
    persist_external_render,
    reference_bytes,
    size_for_aspect,
    standard_size_for_aspect,
)
from studio.paths import logger

# Published 2026-09-08 (developers.openai.com/api/docs/models/gpt-image-2.5-*):
# both 2.5 models bill at the GPT Image 2 token rates — text in $5/M, image
# in $8/M, image out $30/M — and add the `xhigh` / `max` quality tiers.
# Verified live the same day: the 2.5 models REJECT `input_fidelity`
# ("does not support the 'input_fidelity' parameter"), so it is only sent
# for models flagged `input_fidelity: True`; a refusal is retried without it.
_GPT_IMAGE_2_RATES = {"input_text": 5e-6, "input_image": 8e-6, "output_image": 30e-6}
_QUALITIES = ["low", "medium", "high", "xhigh", "max"]
_RESOLUTIONS = ["1K", "2K"]
OPENAI_MODELS = {
    "gpt-image-2.5-flare": {
        "label": "GPT Image 2.5 Flare · OpenAI",
        "max_refs": 16,
        "aspects": list(ALL_ASPECTS),
        "resolutions": _RESOLUTIONS,
        "qualities": _QUALITIES,
        "default_quality": "high",
        "price_hint": "≈$0.01–0.13/obraz przy 1K, wg jakości",
        "rates": _GPT_IMAGE_2_RATES,
        "input_fidelity": False,
        "note_pl": "domyślny wybór: jakość GPT Image 2+, o połowę krótszy czas",
    },
    "gpt-image-2.5-sunburst": {
        "label": "GPT Image 2.5 Sunburst · OpenAI",
        "max_refs": 16,
        "aspects": list(ALL_ASPECTS),
        "resolutions": _RESOLUTIONS,
        "qualities": _QUALITIES,
        "default_quality": "high",
        "price_hint": "≈$0.01–0.13/obraz przy 1K, wg jakości",
        "rates": _GPT_IMAGE_2_RATES,
        "input_fidelity": False,
        "note_pl": "premium: ściślejsza kontrola edycji, produktowe kampanie",
    },
}

_API_BASE = "https://api.openai.com/v1/images"
_TIMEOUT_S = 600


class OpenAIImagesError(ExternalEngineError):
    pass


def _classify(status: int, body: str) -> OpenAIImagesError:
    code, message = "", body
    try:
        err = (json.loads(body) or {}).get("error") or {}
        code = str(err.get("code") or err.get("type") or "")
        message = str(err.get("message") or body)
    except Exception:
        pass
    message = message[:300]
    if status in (401, 403):
        return OpenAIImagesError(
            "Klucz OpenAI jest nieprawidłowy lub nie ma dostępu do Images API.",
            "INVALID_OPENAI_KEY", message, False, 401)
    if status == 429 and "insufficient_quota" in code:
        return OpenAIImagesError("Brak środków na koncie OpenAI — doładuj saldo.",
                                 "OPENAI_NO_CREDITS", message, False, 402)
    if status == 429:
        return OpenAIImagesError("Limit zapytań OpenAI — spróbuj za chwilę.",
                                 "RATE_LIMITED", message, True, 429)
    if status == 400 and ("moderation" in code or "safety" in message.lower()):
        return OpenAIImagesError("OpenAI odrzuciło ten prompt lub referencje (moderacja).",
                                 "OPENAI_BLOCKED", message, False, 400)
    if status == 400:
        return OpenAIImagesError("OpenAI odrzuciło zapytanie — sprawdź szczegóły.",
                                 "OPENAI_BAD_REQUEST", message, False, 400)
    return OpenAIImagesError("Generowanie przez OpenAI nie powiodło się.",
                             "OPENAI_ERROR", message, status >= 500, 502)


def _resolve_quality(model: str, quality: str) -> str:
    cfg = OPENAI_MODELS.get(model, {})
    qualities = cfg.get("qualities") or _QUALITIES
    return quality if quality in qualities else cfg.get("default_quality", "high")


def cost_from_usage(model: str, usage: dict[str, Any]) -> float:
    """USD cost of one call from the Images API `usage` block."""
    rates = OPENAI_MODELS.get(model, {}).get("rates") or _GPT_IMAGE_2_RATES
    details = usage.get("input_tokens_details") or {}
    text_in = float(details.get("text_tokens") or 0)
    image_in = float(details.get("image_tokens") or 0)
    if not details and usage.get("input_tokens"):
        text_in = float(usage.get("input_tokens") or 0)
    out = float(usage.get("output_tokens") or 0)
    return round(
        text_in * rates["input_text"] + image_in * rates["input_image"] + out * rates["output_image"],
        6,
    )


def generate_openai(
    *,
    api_key: str,
    model: str,
    prompt: str,
    aspect: str,
    resolution: str = "1K",
    references: Optional[list[ReferenceItem]] = None,
    quality: str = "",
    png_meta: Optional[dict[str, str]] = None,
    prompt_summary: str = "",
    trace_request: Any = None,
) -> dict:
    """Blocking call (run via asyncio.to_thread). Returns
    {generation_id, output_path, cost, elapsed_ms, model_id, resolution,
    quality, size} or raises OpenAIImagesError."""
    t0 = time.monotonic()
    generation_id = new_generation_id()
    cfg = OPENAI_MODELS.get(model, {"max_refs": 16})
    refs = list(references or [])[: cfg["max_refs"]]
    resolution_used = "2K" if str(resolution or "").upper().startswith("2K") else "1K"
    size = size_for_aspect(aspect, resolution_used)
    quality_used = _resolve_quality(model, quality)
    headers = {"Authorization": f"Bearer {api_key}"}

    send_fidelity = bool(cfg.get("input_fidelity", True))

    def _call(size_value: str):
        try:
            if refs:
                files = []
                for index, (_role, source, image) in enumerate(refs, start=1):
                    raw, mime = reference_bytes(source, image)
                    ext = mime.split("/", 1)[1].replace("jpeg", "jpg")
                    files.append(("image[]", (f"ref{index}.{ext}", raw, mime)))
                data = {
                    "model": model,
                    "prompt": prompt,
                    "size": size_value,
                    "quality": quality_used,
                    "output_format": "png",
                    "n": "1",
                }
                if send_fidelity:
                    data["input_fidelity"] = "high"
                return httpx.post(f"{_API_BASE}/edits", data=data, files=files,
                                  headers=headers, timeout=_TIMEOUT_S)
            body = {
                "model": model,
                "prompt": prompt,
                "size": size_value,
                "quality": quality_used,
                "output_format": "png",
                "n": 1,
            }
            return httpx.post(f"{_API_BASE}/generations", json=body,
                              headers=headers, timeout=_TIMEOUT_S)
        except httpx.HTTPError as exc:
            raise OpenAIImagesError("Błąd sieci przy wywołaniu OpenAI.",
                                    "NETWORK_TIMEOUT", str(exc)[:300], True) from exc

    logger.info("OpenAI request: %s %s size=%s quality=%s refs=%d prompt=%d chars",
                model, "edits" if refs else "generations", size, quality_used,
                len(refs), len(prompt))
    r = _call(size)
    if r.status_code == 400 and send_fidelity and "input_fidelity" in r.text:
        logger.warning("OpenAI %s refused input_fidelity (%s) — retrying without it",
                       model, r.text[:200])
        send_fidelity = False
        r = _call(size)
    if r.status_code == 400 and "size" in r.text.lower() and "input_fidelity" not in r.text:
        # The exact-ratio size was refused (custom sizes are not accepted on
        # every model/endpoint yet): fall back to OpenAI's standard size of
        # the same orientation rather than failing the render.
        fallback = standard_size_for_aspect(aspect)
        if fallback != size:
            logger.warning("OpenAI rejected size %s (%s) — retrying with %s",
                           size, r.text[:300], fallback)
            size = fallback
            r = _call(size)

    if r.status_code >= 400:
        logger.warning("OpenAI %s failed: HTTP %s %s", model, r.status_code, r.text[:600])
        raise _classify(r.status_code, r.text[:600])

    try:
        payload = r.json()
        img_b64 = payload["data"][0]["b64_json"]
        image = Image.open(io.BytesIO(base64.b64decode(img_b64)))
        image.load()
    except Exception as exc:
        raise OpenAIImagesError("OpenAI zwróciło nieczytelną odpowiedź.",
                                "OPENAI_ERROR", str(exc)[:300], True) from exc

    usage = payload.get("usage") or {}
    cost = cost_from_usage(model, usage)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    output_path = persist_external_render(
        image=image,
        engine="openai",
        model=model,
        generation_id=generation_id,
        references=refs,
        cost=cost,
        elapsed_ms=elapsed_ms,
        resolution=resolution_used,
        prompt=prompt,
        prompt_summary=prompt_summary,
        png_meta={**(png_meta or {}), "nano_sofa_quality": quality_used, "nano_sofa_size": size},
        trace_request=trace_request,
        extra_trace={"quality": quality_used, "size": size, "usage": usage,
                     "input_fidelity": "high" if (refs and send_fidelity) else None},
    )
    logger.info("OpenAI render OK: %s %s %s %.1fs $%.4f refs=%d",
                model, size, quality_used, elapsed_ms / 1000, cost, len(refs))
    return {
        "generation_id": generation_id,
        "output_path": output_path,
        "cost": cost,
        "elapsed_ms": elapsed_ms,
        "model_id": model,
        "resolution": resolution_used,
        "quality": quality_used,
        "size": size,
    }


def _failure(req: GenerationRequest, generation_id: str, *, code: str, message: str,
             detail: str = "", retryable: bool = False, http_status: int = 502) -> GenerationResult:
    return GenerationResult(
        success=False, generation_id=generation_id, output_path=None, output_image=None,
        next_history=list(req.prior_history), actual_cost=0.0, attempts=1,
        error_message=message, model_id=req.model_id, resolution=req.resolution,
        error_code=code, error_detail=detail, retryable=retryable, http_status=http_status,
    )


def generate_product_openai(req: GenerationRequest, api_key: str) -> GenerationResult:
    """The product pipeline (base photo + leg / scene / fabric set / colour
    patch / moodboards, the full variant prompt) on the OpenAI Images API —
    what the Lab tab's wizard calls instead of generator.generate(). Same
    plan_reference_slots order with the model's 16-reference cap, same
    _build_prompt_text numbered from the images actually attached, result
    shaped like a Gemini GenerationResult so every route treats it alike."""
    cfg = OPENAI_MODELS.get(req.model_id, {"max_refs": 16})
    base_img = _load_image(req.base_product_image)
    if base_img is None:
        return _failure(req, new_generation_id(), code="BAD_INPUT_IMAGE",
                        message="Nie udało się odczytać zdjęcia bazowego.",
                        detail="Could not load base product image.", http_status=400)
    if req.base_image_has_alpha or base_img.mode in ("RGBA", "LA"):
        base_img = _flatten_alpha(base_img)

    loaded = _load_reference_plan(req, base_img, cfg["max_refs"])
    slots = slot_numbers([slot for slot, _image in loaded])
    prompt = _build_prompt_text(req, slots)
    references = [(slot.role, slot.source, image) for slot, image in loaded]
    png_meta = {
        "nano_sofa_color": req.upholstery_color or "",
        "nano_sofa_material": req.upholstery_material or "",
        "nano_sofa_color_id": req.color_id or "",
        "nano_sofa_material_id": req.material_id or "",
        "nano_sofa_fabric_code": req.fabric_code or "",
        "nano_sofa_color_hex": req.upholstery_hex or "",
        "nano_sofa_leg_id": req.leg_id or "",
    }
    summary = f"{req.upholstery_color} {req.upholstery_material} {req.camera_angle}".strip()
    try:
        out = generate_openai(
            api_key=api_key, model=req.model_id, prompt=prompt, aspect=req.aspect_ratio,
            resolution=req.resolution, references=references, quality=req.engine_quality,
            png_meta=png_meta, prompt_summary=summary, trace_request=req,
        )
    except ExternalEngineError as exc:
        return _failure(req, new_generation_id(), code=exc.code, message=exc.message_pl,
                        detail=exc.detail, retryable=exc.retryable, http_status=exc.http_status)
    output_image = Image.open(out["output_path"])
    output_image.load()
    return GenerationResult(
        success=True, generation_id=out["generation_id"], output_path=out["output_path"],
        output_image=output_image, next_history=list(req.prior_history),
        actual_cost=out["cost"], attempts=1, error_message=None,
        model_id=req.model_id, resolution=out["resolution"], elapsed_ms=out["elapsed_ms"],
    )
