"""Shared plumbing for the non-Gemini image engines.

Two engines live outside `app.core.generator`: the OpenRouter Images API
(`studio/openrouter.py`) and the OpenAI Images API (`studio/openai_images.py`,
the experimental Lab tab). Both receive the same freeform reference plan the
Gemini path gets (fabric macro, exact colour patch, oblique / behaviour /
application views, moodboards — see generator.plan_freeform_reference_slots)
and both end the same way: a lossless PNG master with the self-identifying
tEXt chunks, a cost-DB row and a generation trace, so history, the
Experiments page and retention treat every engine alike.
"""

from __future__ import annotations

import base64
import io
import time
from dataclasses import replace as dataclass_replace
from pathlib import Path
from typing import Any, Optional

from PIL import Image, PngImagePlugin

from app.core.cost_tracker import GenerationRecord, record_generation
from app.core.generation_trace import build_generation_trace, write_generation_trace
from studio.paths import _OUTPUT_DIR, logger

# One attached reference as the route hands it over: (prompt role, source
# label for the trace, loaded image). Produced from
# generator.load_freeform_reference_plan.
ReferenceItem = tuple[str, Any, Image.Image]

# Every aspect the editorial page offers, in its own order.
ALL_ASPECTS = ["1:1", "3:4", "4:3", "2:3", "3:2", "9:16", "16:9", "21:9"]

# Pixel sizes for engines that take explicit WIDTHxHEIGHT (OpenAI). Every
# edge is a multiple of 16 and the ratio is exact; the 1:1 / 3:2 / 2:3 rows
# are OpenAI's own recommended sizes. "2K" scales each edge by 1.5 (still
# multiples of 16, longest edge 3024 ≤ the 3840 limit).
_ASPECT_SIZES_1K: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "3:4": (1152, 1536),
    "4:3": (1536, 1152),
    "2:3": (1024, 1536),
    "3:2": (1536, 1024),
    "4:5": (1024, 1280),
    "9:16": (864, 1536),
    "16:9": (1536, 864),
    "21:9": (2016, 864),
}


def standard_size_for_aspect(aspect: str) -> str:
    """OpenAI's three documented sizes, picked by orientation — the fallback
    when an exact-ratio custom size is refused."""
    try:
        w, h = (int(v) for v in aspect.split(":"))
    except ValueError:
        return "1024x1024"
    if w > h:
        return "1536x1024"
    if h > w:
        return "1024x1536"
    return "1024x1024"


def size_for_aspect(aspect: str, resolution: str = "1K") -> str:
    width, height = _ASPECT_SIZES_1K.get(aspect) or _ASPECT_SIZES_1K["1:1"]
    scale = 1.5 if str(resolution or "").strip().upper().startswith("2K") else 1.0
    return f"{int(width * scale)}x{int(height * scale)}"


class ExternalEngineError(Exception):
    """Classified, user-facing failure of an external engine call."""

    def __init__(self, message_pl: str, code: str, detail: str = "", retryable: bool = False,
                 http_status: int = 502):
        super().__init__(message_pl)
        self.message_pl = message_pl
        self.code = code
        self.detail = detail
        self.retryable = retryable
        self.http_status = http_status


def reference_bytes(source: Any, image: Image.Image) -> tuple[bytes, str]:
    """Encoded bytes + mime for one reference. File-backed references are
    sent as stored (the curated swatches are already JPEG ≤ 2048 px);
    in-memory ones (the colour patch) are encoded as PNG."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.is_file():
            suffix = path.suffix.lower().lstrip(".")
            mime = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix or 'png'}"
            return path.read_bytes(), mime
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue(), "image/png"


def reference_data_url(source: Any, image: Image.Image) -> str:
    raw, mime = reference_bytes(source, image)
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def persist_external_render(
    *,
    image: Image.Image,
    engine: str,
    model: str,
    generation_id: str,
    references: list[ReferenceItem],
    cost: float,
    elapsed_ms: int,
    resolution: str,
    prompt: str,
    prompt_summary: str = "",
    png_meta: Optional[dict[str, str]] = None,
    trace_request: Any = None,
    extra_trace: Optional[dict[str, Any]] = None,
) -> Path:
    """Save the PNG master (same naming scheme and tEXt chunks as the Gemini
    path), record the cost row and write the generation trace. Neither the
    cost row nor the trace may break a successful render."""
    ts = int(time.time())
    safe_model = model.replace("/", "-").replace(".", "-")
    output_path = _OUTPUT_DIR / f"{ts}_{safe_model}_{generation_id[:8]}.png"
    pnginfo = PngImagePlugin.PngInfo()
    meta = {
        "nano_sofa_schema": "1",
        "nano_sofa_generation_id": generation_id,
        "nano_sofa_ts": str(ts),
        "nano_sofa_model": model,
        "nano_sofa_engine": engine,
        "nano_sofa_resolution": resolution,
        "nano_sofa_prompt_summary": prompt_summary[:500],
        **(png_meta or {}),
    }
    for key, value in meta.items():
        pnginfo.add_text(key, str(value))
    image.save(output_path, format="PNG", optimize=True, pnginfo=pnginfo)

    try:
        record_generation(GenerationRecord(
            generation_id=generation_id,
            timestamp=time.time(),
            model_id=model,
            resolution=resolution,
            num_ref_images=len(references),
            actual_cost=cost,
            status="success",
            output_path=str(output_path),
            error_message=None,
            prompt_summary=prompt_summary[:500],
            leg_id=None,
            upholstery_color=(png_meta or {}).get("nano_sofa_color", ""),
            upholstery_material=(png_meta or {}).get("nano_sofa_material", ""),
            camera_angle="",
            turn_number=1,
            elapsed_ms=elapsed_ms,
        ))
    except Exception:  # the cost DB must never break a successful render
        logger.exception("%s: cost record failed", engine)

    if trace_request is not None:
        try:
            trace = build_generation_trace(
                req=dataclass_replace(trace_request, model_id=model, resolution=resolution),
                generation_id=generation_id,
                prompt=prompt,
                effective_system_instruction="",
                reference_images=[img for _role, _source, img in references],
                freeform=True,
                reference_roles=[(role, source) for role, source, _img in references],
            )
            trace["engine"] = engine
            trace.update(extra_trace or {})
            trace["status"] = "success"
            trace["result"] = {
                "output_path": str(output_path),
                "actual_cost": cost,
                "estimated_cost_low": cost,
                "estimated_cost_high": cost,
                "elapsed_ms": elapsed_ms,
                "attempts": 1,
                "error": None,
            }
            write_generation_trace(trace, _OUTPUT_DIR / "traces")
        except Exception:
            logger.exception("%s: trace write failed", engine)
    return output_path
