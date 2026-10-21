"""Builders that FILL a PromptSpec.

product_spec(req, slots)   — from a GenerationRequest (the product pipeline)
freeform_spec(...)         — from resolved editorial picker texts

Both end in the same compile_prompt(); the engines never see a request,
only the compiled text.
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.prompt.spec import (
    CameraSpec,
    ColourSpec,
    EditorialSpec,
    MaterialSpec,
    ProductSpec,
    PromptSpec,
    SceneSpec,
)


def product_spec(req: Any, slots: dict[str, int]) -> PromptSpec:
    """`req` is a generator.GenerationRequest (typed as Any to keep this
    package free of the engine module)."""
    noun = "bed" if req.product_type == "bed" else "sofa"
    model_id = getattr(req, "model_id", "") or ""
    return PromptSpec(
        mode="product",
        engine="gpt" if "gpt-image" in model_id else "gemini",
        slots=dict(slots),
        product=ProductSpec(
            noun=noun,
            configuration=req.sofa_configuration or "",
            frame_style=req.frame_style,
            leg_count=int(req.leg_count),
            preserve=list(req.preserve_list),
            leg_id=req.leg_id,
            leg_explicit_descriptor=req.leg_explicit_descriptor or "",
            leg_instruction=req.leg_instruction or "",
            bedding=req.bedding_description or "",
        ),
        material=MaterialSpec(
            noun=req.upholstery_material or "",
            spec=req.texture_notes or "",
            avoid=list(req.negative_list),
            structure=getattr(req, "material_structure", "") or "",
        ),
        colour=ColourSpec(text=req.upholstery_color or "", hex=req.upholstery_hex or ""),
        camera=CameraSpec(
            angle_label=req.camera_angle or "",
            degrees=int(req.angle_degrees_from_left),
            focal_mm=int(req.focal_length_mm),
            aperture=req.aperture or "",
            framing=req.framing or "",
            shot_type=req.shot_type or "hero",
            lens_descriptor=req.lens_descriptor or "",
            preserve_from_base=bool(req.preserve_camera_from_base),
        ),
        scene=SceneSpec(
            mode=req.env_mode or "",
            description=req.env_description or "",
            tod=req.tod_description or "",
            shadow_description=req.shadow_description or "",
            shadow_direction=req.shadow_direction or "",
            keep_source_scene=bool(req.keep_source_scene),
            contains_product=bool(req.scene_contains_product),
            view_consistency=bool(req.view_consistency),
        ),
        strict_in_place_recolor=bool(req.strict_in_place_recolor),
        lock_to_reference=bool(req.lock_to_reference),
        use_swatch_for_fabric=bool(req.use_swatch_for_fabric),
        swatch_texture_only=bool(req.swatch_texture_only),
        catalog_framing_contract=req.catalog_framing_contract or "",
        output_style=req.output_style or "",
        notes=req.notes or "",
    )


def freeform_spec(
    *,
    text: str,
    art_direction: str = "",
    setting_text: str = "",
    light_text: str = "",
    lens_descriptor: str = "",
    height_phrase: str = "",
    color_en: str = "",
    mat_noun_en: str = "",
    mat_texture_en: str = "",
    mat_avoid_en: Optional[list[str]] = None,
    people_text: str = "",
    seed: str = "",
    slots: Optional[dict[str, int]] = None,
    color_hex: str = "",
) -> PromptSpec:
    """Every argument is already an English fragment; resolving picker ids
    to text stays in studio/mappings (the tables live there)."""
    return PromptSpec(
        mode="freeform",
        slots=dict(slots or {}),
        material=MaterialSpec(noun=mat_noun_en, spec=mat_texture_en, avoid=list(mat_avoid_en or [])),
        colour=ColourSpec(text=color_en, hex=color_hex),
        camera=CameraSpec(lens_descriptor=lens_descriptor, height_phrase=height_phrase),
        scene=SceneSpec(setting_text=setting_text, light_text=light_text),
        editorial=EditorialSpec(brief=text, art_direction=art_direction,
                                people_text=people_text, seed=seed),
    )
