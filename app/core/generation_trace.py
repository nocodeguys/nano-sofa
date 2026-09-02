"""Reproducible, key-free manifests for image-generation experiments."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterable

from PIL import Image


TRACE_SCHEMA_VERSION = 1


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_label(source: Any) -> str:
    if isinstance(source, (str, Path)):
        return str(Path(source))
    return "<in-memory-image>"


def _image_sha256(image: Image.Image) -> str:
    rgb = image.convert("RGB")
    header = f"RGB:{rgb.width}x{rgb.height}:".encode("ascii")
    return hashlib.sha256(header + rgb.tobytes()).hexdigest()


def reference_roles(req: Any, *, freeform: bool = False) -> list[tuple[str, Any]]:
    """Return the declared reference order without exposing request secrets."""
    if freeform:
        return [
            (f"extra_reference_{idx}", source)
            for idx, source in enumerate(req.extra_reference_images or [], start=1)
        ]

    declared = [
        ("base_product", req.base_product_image),
        ("leg", req.leg_reference_image),
        ("scene", req.scene_reference_image),
        ("material_macro", req.swatch_reference_image),
        ("material_left", req.material_left_reference_image),
        ("material_right", req.material_right_reference_image),
        ("material_behavior", req.material_behavior_reference_image),
        ("material_application", req.material_application_reference_image),
    ]
    active = [(role, source) for role, source in declared if source is not None]
    active.extend(
        (f"extra_reference_{idx}", source)
        for idx, source in enumerate(req.extra_reference_images or [], start=1)
    )
    return active


def build_generation_trace(
    *,
    req: Any,
    generation_id: str,
    prompt: str,
    effective_system_instruction: str,
    reference_images: Iterable[Image.Image],
    freeform: bool = False,
) -> dict[str, Any]:
    """Build the immutable input portion of a generation manifest.

    Only an explicit allow-list of request fields is serialized, so API keys and
    conversation history can never leak into the trace.
    """
    images = list(reference_images)
    roles = reference_roles(req, freeform=freeform)
    references = []
    for slot, (image, role_source) in enumerate(zip(images, roles), start=1):
        role, source = role_source
        references.append(
            {
                "slot": slot,
                "role": role,
                "source": _source_label(source),
                "width": image.width,
                "height": image.height,
                "sha256_rgb": _image_sha256(image),
            }
        )

    prompt_sha = _sha256_text(prompt)
    system_sha = _sha256_text(effective_system_instruction)
    ref_signature = [
        {"slot": ref["slot"], "role": ref["role"], "sha256_rgb": ref["sha256_rgb"]}
        for ref in references
    ]
    setup_payload = {
        "prompt_sha256": prompt_sha,
        "system_instruction_sha256": system_sha,
        "references": ref_signature,
        "aspect_ratio": req.aspect_ratio,
    }
    exact_payload = {
        **setup_payload,
        "model_id": req.model_id,
        "resolution": req.resolution,
    }

    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "generation_id": generation_id,
        "created_at": time.time(),
        "status": "prepared",
        "model_id": req.model_id,
        "resolution": req.resolution,
        "aspect_ratio": req.aspect_ratio,
        "variant": {
            "product_type": req.product_type,
            "material": req.upholstery_material,
            "color": req.upholstery_color,
            "camera_angle": req.camera_angle,
            "shot_type": req.shot_type,
        },
        "prompt": prompt,
        "prompt_sha256": prompt_sha,
        "system_instruction_sha256": system_sha,
        "setup_fingerprint": _fingerprint(setup_payload),
        "exact_fingerprint": _fingerprint(exact_payload),
        "references": references,
        "result": {},
    }


def write_generation_trace(trace: dict[str, Any], trace_dir: Path) -> Path:
    """Atomically persist a trace and return its path."""
    trace_dir.mkdir(parents=True, exist_ok=True)
    destination = trace_dir / f"{trace['generation_id']}.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination
