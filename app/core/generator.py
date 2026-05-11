"""
generator.py — Assembles prompts from form state and calls the Gemini API.

Handles:
- Alpha-channel flattening (base_image_has_alpha flag)
- Reference slot assembly in declared order
- Exponential backoff retry for known 30–45% peak-hour failure rates
- Thought-signature extraction for multi-turn sessions
- Cost recording after each call
"""

from __future__ import annotations

import io
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from PIL import Image

from app.core.cost_tracker import (
    GenerationRecord,
    estimate_cost,
    new_generation_id,
    record_generation,
)
from app.core.leg_browser import leg_browser
from app.core.schema_loader import schema

logger = logging.getLogger(__name__)

_OUTPUTS_DIR = Path(__file__).resolve().parents[1] / "outputs"
_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Retry configuration for known peak-hour failure rates
_MAX_RETRIES = 4
_BACKOFF_BASE_SECONDS = 2.0
_BACKOFF_MAX_SECONDS = 30.0

# 18% sRGB neutral grey (#7F7F7F) — matches legs/STANDARDS.md so flattened
# base products and leg-library renders share the same background value.
_ALPHA_FLATTEN_GREY = (127, 127, 127)


@dataclass
class GenerationRequest:
    """All parameters needed for a single generation call."""

    # Model
    model_id: str

    # Reference images (paths or PIL Images)
    base_product_image: Any   # PIL.Image or path string
    leg_reference_image: Optional[Any] = None   # PIL.Image or path string
    scene_reference_image: Optional[Any] = None
    swatch_reference_image: Optional[Any] = None

    # Product
    product_type: str = "sofa"   # "sofa" | "bed"
    sofa_configuration: str = "3-seater"   # also used for bed sizes when product_type == "bed"
    frame_style: Optional[str] = None      # bed-only: platform, panel, sleigh, etc.
    leg_count: int = 4   # sofa default 4. bed default should be set by caller (0 for platform/divan)
    preserve_list: list[str] = field(default_factory=list)

    # Variant
    upholstery_color: str = "sage green"
    upholstery_material: str = "bouclé"
    texture_notes: str = ""
    base_image_has_alpha: bool = False

    # Legs
    leg_id: Optional[str] = None
    leg_explicit_descriptor: str = ""
    leg_instruction: str = ""

    # Camera
    camera_angle: str = "front-34-left"
    angle_degrees_from_left: int = 35
    shadow_direction: str = "4 o-clock"
    focal_length_mm: int = 50
    aperture: str = "f/4.5"
    framing: str = "full product visible with breathing room above and below"

    # Output
    aspect_ratio: str = "4:3"
    resolution: str = "1K"
    output_style: str = "e-commerce hero photography, photorealistic, neutral color grading"

    # System + negative
    system_instruction: str = ""
    negative_list: list[str] = field(default_factory=list)

    # Notes
    notes: str = ""

    # API key — per-user, supplied via the UI. Falls back to GEMINI_API_KEY
    # environment variable only when this field is empty.
    api_key: str = ""

    # Multi-turn
    # prior_history is an opaque list of google.genai.types.Content objects from
    # earlier turns in this chain (alternating user/model). On each new turn,
    # generate() prepends them to the contents list so the model sees the full
    # conversation including thought_signature parts on prior model turns —
    # the documented mitigation for identity drift in multi-turn edits.
    turn_number: int = 1
    prior_history: list[Any] = field(default_factory=list)


@dataclass
class GenerationResult:
    """Result of a single generation call."""
    success: bool
    generation_id: str
    output_path: Optional[Path]
    output_image: Optional[Image.Image]
    # next_history is the prior_history extended with the user Content sent on
    # this call and the model Content received in response (which carries any
    # thought_signature parts). Pass it back as prior_history on the next turn
    # to maintain context.
    next_history: list[Any]
    actual_cost: float
    attempts: int
    error_message: Optional[str]
    model_id: str
    resolution: str


def _flatten_alpha(img: Image.Image) -> Image.Image:
    """
    Flatten any alpha channel to 18% neutral grey.
    Mitigates background-bleed failure mode when transparent-background PNGs
    are passed as reference images.
    """
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        background = Image.new("RGB", img.size, _ALPHA_FLATTEN_GREY)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[3])
        logger.info("Alpha channel detected and flattened to 18%% grey (%s px)", img.size)
        return background
    return img.convert("RGB") if img.mode != "RGB" else img


def _load_image(source: Any) -> Optional[Image.Image]:
    """Load a PIL Image from a path string, Path, or return as-is if already PIL."""
    if source is None:
        return None
    if isinstance(source, Image.Image):
        return source
    try:
        return Image.open(str(source))
    except Exception as exc:
        logger.warning("Could not load image from %r: %s", source, exc)
        return None


def _count_active_refs(req: GenerationRequest) -> int:
    count = 1  # base product is always slot 1
    if req.leg_reference_image is not None:
        count += 1
    if req.scene_reference_image is not None:
        count += 1
    if req.swatch_reference_image is not None:
        count += 1
    return count


def _build_prompt_text(req: GenerationRequest) -> str:
    """
    Assemble the full prompt text from the request fields.
    Branches on req.product_type so anatomy nouns are correct (sofa vs bed)
    and so leg-count emphasis is OMITTED entirely when leg_count is 0
    (the proximate cause of the model adding legs to platform beds).
    """
    lines: list[str] = []

    is_bed = req.product_type == "bed"
    product_noun = "bed" if is_bed else "sofa"
    legs_visible = req.leg_count > 0
    has_leg_swap = bool(req.leg_id or req.leg_explicit_descriptor)

    # ------------------------------------------------------------------ #
    # Primary instruction
    # ------------------------------------------------------------------ #
    lines.append(
        f"Edit the {product_noun} in the first reference image to produce a product "
        f"photography variant with the following specifications."
    )
    lines.append(
        f"This is a {product_noun}, not any other furniture type. "
        f"Render anatomy and proportions consistent with a {product_noun}."
    )

    # ------------------------------------------------------------------ #
    # Bed-specific: frame style + size context
    # ------------------------------------------------------------------ #
    if is_bed:
        if req.frame_style:
            frame_label = req.frame_style.replace("-", " ")
            lines.append(
                f"\nFRAME STYLE: {frame_label} bed frame. "
                f"Render the frame silhouette consistent with a {frame_label} construction. "
                f"Do not invent footboards, posts, canopies, or storage drawers that are "
                f"not present in the base reference image and not stated here."
            )
        if req.sofa_configuration:
            lines.append(
                f"BED SIZE: {req.sofa_configuration}. "
                f"Maintain the proportions of a {req.sofa_configuration} bed."
            )

    # ------------------------------------------------------------------ #
    # Upholstery / surface
    # ------------------------------------------------------------------ #
    surface_noun = "UPHOLSTERY / FRAME FINISH" if is_bed else "UPHOLSTERY"
    lines.append(
        f"\n{surface_noun}: {req.upholstery_color} {req.upholstery_material}."
    )
    if req.texture_notes:
        lines.append(f"Texture detail: {req.texture_notes}")

    # ------------------------------------------------------------------ #
    # Legs — only when relevant (leg_count > 0 OR explicit leg swap)
    # ------------------------------------------------------------------ #
    if has_leg_swap:
        # User picked a specific leg style from the manifest
        leg_instruction = req.leg_instruction or (
            f"Replace ONLY the legs with the leg style shown in the reference image. "
            + (
                f"The {product_noun} has exactly {req.leg_count} legs. "
                if legs_visible else
                f"Apply the leg style consistent with the {product_noun}'s frame. "
            )
            + f"Do not add braces, brackets, or structural elements not present in the "
            f"leg reference. Match the {product_noun}'s perspective and scale. "
            f"Keep contact shadow consistent with the scene lighting direction. "
            f"Do not modify the {product_noun} frame, "
            + ("cushions, upholstery, or stitching." if not is_bed else "headboard, mattress, or bedding.")
        )
        leg_instruction = leg_instruction.replace("[leg_count]", str(req.leg_count))
        lines.append(f"\nLEGS: {leg_instruction}")
        if req.leg_explicit_descriptor:
            lines.append(
                f"Leg style description (use this alongside the reference image): "
                f"{req.leg_explicit_descriptor}"
            )
    elif legs_visible:
        # Legs are visible in the base photo and we're keeping them
        lines.append(
            f"\nLEGS: Preserve the existing leg style exactly. "
            f"The {product_noun} has exactly {req.leg_count} legs — "
            f"do not add, remove, or merge any legs."
        )
    else:
        # No legs visible (typical platform bed). DO NOT mention legs at all —
        # mentioning leg-count even as "0 legs" can prime the model to add them.
        if is_bed:
            lines.append(
                f"\nFRAME BASE: The {product_noun} sits on a frame without visible legs "
                f"(platform-style construction). Do not add visible legs, feet, posts, "
                f"or risers under the {product_noun}."
            )

    # ------------------------------------------------------------------ #
    # Camera angle — stated explicitly even when reference is attached
    # ------------------------------------------------------------------ #
    angle_label = req.camera_angle.replace("-", " ")
    lines.append(
        f"\nCAMERA: {angle_label} view, approximately {req.angle_degrees_from_left} degrees "
        f"from the left. "
        f"Focal length equivalent {req.focal_length_mm} mm, {req.aperture} aperture. "
        f"Framing: {req.framing}."
    )

    # ------------------------------------------------------------------ #
    # Shadow direction — required for leg swap and scene ref
    # ------------------------------------------------------------------ #
    if req.shadow_direction:
        shadow_text = (
            f"Shadow direction: the shadow cast by the {product_noun} falls at "
            f"{req.shadow_direction} (clock position from the {product_noun}'s perspective)."
        )
        if legs_visible or has_leg_swap:
            shadow_text += " All leg contact shadows must be consistent with this direction."
        lines.append(shadow_text)

    # ------------------------------------------------------------------ #
    # Scene reference
    # ------------------------------------------------------------------ #
    if req.scene_reference_image is not None:
        lines.append(
            f"\nSCENE: Place the {product_noun} naturally within the scene shown in the "
            f"reference image. Match lighting direction, color temperature, and floor "
            f"material from the scene reference. The shadow beneath the {product_noun} "
            f"must fall in the same direction as all other shadows in the scene."
        )
    else:
        lines.append(
            "\nSCENE: Neutral studio backdrop. Clean, professional e-commerce photography background."
        )

    # ------------------------------------------------------------------ #
    # Preserve list
    # ------------------------------------------------------------------ #
    if req.preserve_list:
        preserve_readable = [p.replace("_", " ") for p in req.preserve_list]
        lines.append(
            f"\nPRESERVE — do NOT change any of the following: "
            + ", ".join(preserve_readable) + "."
        )
        # Repeat leg-count emphasis ONLY when legs are actually visible.
        if legs_visible:
            lines.append(
                f"The {product_noun} has exactly {req.leg_count} legs. "
                f"Leg count is {req.leg_count} — do not add, remove, or merge legs."
            )

    # ------------------------------------------------------------------ #
    # Output style
    # ------------------------------------------------------------------ #
    lines.append(f"\nOUTPUT STYLE: {req.output_style}")

    # ------------------------------------------------------------------ #
    # Negative list
    # ------------------------------------------------------------------ #
    negatives = list(req.negative_list)
    # When legs are NOT visible on a bed, explicitly negate legs at the
    # negative-list level too — the strongest signal we have.
    if is_bed and not legs_visible and not has_leg_swap:
        negatives = [
            "added legs",
            "added feet",
            "added posts",
            "added risers under the bed",
            "frame raised on visible supports",
        ] + negatives

    if negatives:
        lines.append(
            f"\nNEGATIVE (must not appear in output): "
            + "; ".join(negatives) + "."
        )

    # ------------------------------------------------------------------ #
    # Optional free-form notes
    # ------------------------------------------------------------------ #
    if req.notes:
        lines.append(f"\nADDITIONAL NOTES: {req.notes}")

    return "\n".join(lines)


def _collect_reference_images(
    req: GenerationRequest, base_img: Image.Image
) -> list[Image.Image]:
    """
    Return reference images in declared slot order:
    Slot 1: base product (already flattened by caller)
    Slot 2: leg reference (when present)
    Slot 3: scene reference (when present; on Flash this exhausts the 3-ref cap)
    Slot 4: swatch reference (preview models only — dropped on Flash)
    """
    images: list[Image.Image] = [base_img]

    if req.leg_reference_image is not None:
        leg_img = _load_image(req.leg_reference_image)
        if leg_img:
            images.append(leg_img)

    if req.scene_reference_image is not None:
        scene_img = _load_image(req.scene_reference_image)
        if scene_img:
            images.append(scene_img)

    if req.swatch_reference_image is not None:
        max_refs = schema.max_refs_for_model(req.model_id)
        active_refs = _count_active_refs(req)
        if active_refs <= max_refs:
            swatch_img = _load_image(req.swatch_reference_image)
            if swatch_img:
                images.append(swatch_img)
        else:
            logger.warning(
                "Swatch reference dropped: model %s allows max %d refs, already at %d",
                req.model_id,
                max_refs,
                active_refs,
            )

    return images


def _pil_to_part(img: Image.Image, gtypes) -> Any:
    """Convert a PIL image to a google.genai.types.Part with PNG bytes."""
    buf = io.BytesIO()
    rgb = img if img.mode == "RGB" else img.convert("RGB")
    rgb.save(buf, format="PNG")
    return gtypes.Part.from_bytes(data=buf.getvalue(), mime_type="image/png")


def generate(req: GenerationRequest) -> GenerationResult:
    """
    Main entry point. Calls the Gemini API with retry logic.
    Saves the output image to disk and records cost.
    """
    generation_id = new_generation_id()
    num_refs = _count_active_refs(req)
    cost_est = estimate_cost(req.model_id, req.resolution, num_refs)

    # ------------------------------------------------------------------ #
    # Alpha-channel flattening
    # ------------------------------------------------------------------ #
    base_img = _load_image(req.base_product_image)
    if base_img is None:
        return GenerationResult(
            success=False,
            generation_id=generation_id,
            output_path=None,
            output_image=None,
            next_history=list(req.prior_history),
            actual_cost=0.0,
            attempts=0,
            error_message="Could not load base product image.",
            model_id=req.model_id,
            resolution=req.resolution,
        )

    if req.base_image_has_alpha or base_img.mode in ("RGBA", "LA"):
        base_img = _flatten_alpha(base_img)
        logger.info("Base product image flattened from alpha (alpha bleed mitigation)")

    ref_images = _collect_reference_images(req, base_img)
    prompt_text = _build_prompt_text(req)

    # ------------------------------------------------------------------ #
    # API call with exponential backoff
    # ------------------------------------------------------------------ #
    # Prefer the per-request key supplied via the UI; fall back to env only
    # for legacy / scripted use. Never log the key.
    api_key = (req.api_key or "").strip() or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return GenerationResult(
            success=False,
            generation_id=generation_id,
            output_path=None,
            output_image=None,
            next_history=list(req.prior_history),
            actual_cost=0.0,
            attempts=0,
            error_message=(
                "Brak klucza API. Wklej swój klucz Gemini API w polu na górze "
                "strony (sekcja \"Klucz API\") i spróbuj ponownie."
            ),
            model_id=req.model_id,
            resolution=req.resolution,
        )

    try:
        from google import genai
        from google.genai import types as gtypes
    except ImportError:
        return GenerationResult(
            success=False,
            generation_id=generation_id,
            output_path=None,
            output_image=None,
            next_history=list(req.prior_history),
            actual_cost=0.0,
            attempts=0,
            error_message=(
                "google-genai package not installed. Run: pip install google-genai"
            ),
            model_id=req.model_id,
            resolution=req.resolution,
        )

    client = genai.Client(api_key=api_key)

    # Build the user-turn Content explicitly so we can preserve it in the
    # conversation history alongside the model's response (which carries
    # thought_signature parts on its parts).
    user_parts = [gtypes.Part.from_text(text=prompt_text)]
    for img in ref_images:
        user_parts.append(_pil_to_part(img, gtypes))
    user_content = gtypes.Content(role="user", parts=user_parts)

    contents = list(req.prior_history) + [user_content]

    # Build ImageConfig.
    # google-genai 2.0.0 renamed the resolution kwarg to `image_size`. The
    # accepted vocabulary is unchanged: "1K" / "2K" / "4K". Keeping
    # GenerationRequest.resolution as the public field name so callers don't
    # have to learn the SDK quirk.
    image_config_kwargs: dict[str, Any] = {"aspect_ratio": req.aspect_ratio}
    if schema.supports_resolution_param(req.model_id) and req.resolution != "1K":
        image_config_kwargs["image_size"] = req.resolution

    config = gtypes.GenerateContentConfig(
        system_instruction=req.system_instruction or schema.system_instruction_default,
        response_modalities=["IMAGE"],
        image_config=gtypes.ImageConfig(**image_config_kwargs),
    )

    last_error: str = ""
    output_image: Optional[Image.Image] = None
    model_content: Optional[Any] = None
    attempts_made = 0

    for attempt in range(1, _MAX_RETRIES + 1):
        attempts_made = attempt
        try:
            logger.info(
                "Calling %s (attempt %d/%d, %d refs, history depth=%d)",
                req.model_id,
                attempt,
                _MAX_RETRIES,
                num_refs,
                len(req.prior_history),
            )
            response = client.models.generate_content(
                model=req.model_id,
                contents=contents,
                config=config,
            )

            model_content = response.candidates[0].content

            for part in model_content.parts:
                if part.inline_data and part.inline_data.data:
                    output_image = Image.open(io.BytesIO(part.inline_data.data))
                    break

            if output_image is None:
                last_error = "API returned a response but no image data was present."
                logger.warning("Attempt %d: no image in response — %s", attempt, last_error)
                if attempt < _MAX_RETRIES:
                    _sleep_backoff(attempt)
                continue

            # Success
            break

        except Exception as exc:
            last_error = str(exc)
            logger.warning("Attempt %d failed: %s", attempt, last_error)
            if attempt < _MAX_RETRIES:
                _sleep_backoff(attempt)

    # ------------------------------------------------------------------ #
    # Persist output
    # ------------------------------------------------------------------ #
    output_path: Optional[Path] = None
    status = "failed"
    actual_cost = 0.0

    if output_image is not None:
        ts = int(time.time())
        filename = f"{ts}_{req.model_id.replace('.', '-')}_{generation_id[:8]}.png"
        output_path = _OUTPUTS_DIR / filename
        output_image.save(str(output_path), format="PNG")
        status = "success"
        actual_cost = cost_est.total_low  # use conservative (low) estimate as actual

    # Extend the chain only if we got a usable response. On failure, return the
    # caller's prior_history unchanged so the next retry doesn't pollute the
    # conversation with a failed turn.
    if output_image is not None and model_content is not None:
        next_history = list(req.prior_history) + [user_content, model_content]
    else:
        next_history = list(req.prior_history)

    record_generation(
        GenerationRecord(
            generation_id=generation_id,
            timestamp=time.time(),
            model_id=req.model_id,
            resolution=req.resolution,
            num_ref_images=num_refs,
            actual_cost=actual_cost,
            status=status,
            output_path=str(output_path) if output_path else None,
            error_message=last_error if status == "failed" else None,
            prompt_summary=_build_prompt_summary(req),
            leg_id=req.leg_id,
            upholstery_color=req.upholstery_color,
            upholstery_material=req.upholstery_material,
            camera_angle=req.camera_angle,
            turn_number=req.turn_number,
        )
    )

    return GenerationResult(
        success=output_image is not None,
        generation_id=generation_id,
        output_path=output_path,
        output_image=output_image,
        next_history=next_history,
        actual_cost=actual_cost,
        attempts=attempts_made,
        error_message=last_error if output_image is None else None,
        model_id=req.model_id,
        resolution=req.resolution,
    )


def _sleep_backoff(attempt: int) -> None:
    delay = min(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), _BACKOFF_MAX_SECONDS)
    logger.info("Backing off %.1f seconds before retry...", delay)
    time.sleep(delay)


def _build_prompt_summary(req: GenerationRequest) -> str:
    parts = [
        req.upholstery_color,
        req.upholstery_material,
        req.leg_id or "existing-legs",
        req.camera_angle,
        req.resolution,
    ]
    return " | ".join(parts)


def validate_request(req: GenerationRequest) -> list[str]:
    """
    Return a list of validation error strings. Empty list = valid.
    Called before submission to surface errors in the UI without making an API call.
    """
    errors: list[str] = []

    # Model must be in the schema enum
    if req.model_id not in schema.model_ids:
        errors.append(f"Unknown model ID: {req.model_id!r}. Must be one of: {schema.model_ids}")

    # Resolution ceiling per model
    allowed_resolutions = schema.resolution_choices_for_model(req.model_id)
    if req.resolution not in allowed_resolutions:
        errors.append(
            f"Resolution {req.resolution!r} is not available on {req.model_id}. "
            f"Allowed: {allowed_resolutions}"
        )

    # Reference slot ceiling
    num_refs = _count_active_refs(req)
    max_refs = schema.max_refs_for_model(req.model_id)
    if num_refs > max_refs:
        errors.append(
            f"Too many reference images: {num_refs} slots filled but {req.model_id} "
            f"allows a maximum of {max_refs}. Remove slot 4 (swatch) or use a preview-tier model."
        )

    # Shadow direction required when legs or scene are swapped
    has_leg_swap = req.leg_id is not None
    has_scene = req.scene_reference_image is not None
    if (has_leg_swap or has_scene) and not req.shadow_direction:
        errors.append(
            "Shadow direction is required when a leg or scene reference is active. "
            "Fill the shadow direction field (e.g. '4 o-clock')."
        )

    # On Flash (3-ref cap), the swatch slot is reachable only when the total
    # active refs are still <= 3. The total-refs check above handles this; no
    # separate "preview only" rule is needed (the schema's slot_3_scene_or_swatch
    # explicitly allows swatch in slot 3 on Flash when scene is absent).

    # Preserve list must not be empty
    if not req.preserve_list:
        errors.append("Preserve list must contain at least one item.")

    # Base image required
    if req.base_product_image is None:
        errors.append("A base product image is required (slot 1).")

    # Multi-turn chain-reset warning (not an error, but surfaces as warning)
    if req.turn_number > 3:
        errors.append(
            f"WARNING: Turn {req.turn_number} exceeds the recommended chain length of 3. "
            "Identity drift (stitching, leg joinery) is expected at this turn depth. "
            "Save the current output and start a new chain with it as the base reference."
        )

    return errors
