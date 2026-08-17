"""FormData → GenerationRequest translation.

_build_generation_request is the single funnel every render endpoint goes
through; _recolor_request is its keep-source-scene wrapper for the Fotosesja
grid. Resolves legacy Polish UI strings via the alias tables so stale browser
caches keep working.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.core.generator import GenerationRequest
from studio.catalog import _COLOR_PL_TO_EN, _MATERIAL_PL_TO_EN, _MATERIAL_TEXTURE_EN
from studio.mappings import (
    _BED_CONFIG,
    _CAM_PRESET_TO_STRUCTURED,
    _CLOSE_REGION_DEFAULT_BED,
    _CLOSE_REGION_DEFAULT_SOFA,
    _DETAIL_REGION_DEFAULT_CORNER,
    _DETAIL_REGION_DEFAULT_FABRIC,
    _DETAIL_REGION_TO_PHRASE,
    _DOF_TO_APERTURE,
    _ENV_TO_SCENE,
    _HEIGHT_TO_PHRASE,
    _LEG_TO_ID,
    _LENS_DEFAULT,
    _LENS_LEGACY_ALIAS,
    _LENS_TO_PROMPT,
    _SHADOW_DEFAULT,
    _SHADOW_LEGACY_ALIAS,
    _SHADOW_TO_PROMPT,
    _SHOT_TYPE_TO_FRAMING,
    _SOFA_CONFIG,
    _TOD_LEGACY_ALIAS,
    _TOD_TO_PROMPT,
    _YAW_TO_ANGLE,
    _resolve_id,
)
from studio.paths import _SCENE_REFS_DIR, logger


def _scene_reference_path(env_id: str) -> Optional[Path]:
    """Return the curated reference image path for an env id, if one exists."""
    if not env_id:
        return None
    for ext in (".jpg", ".jpeg", ".png"):
        candidate = _SCENE_REFS_DIR / f"{env_id}{ext}"
        if candidate.is_file():
            return candidate
    return None


def _build_generation_request(
    *,
    api_key: str,
    kind: str,
    color: str, color_custom: str,
    mat: str, mat_notes: str,
    size: str,
    legs: str,
    cam: str,
    lens: str, tod: str, shadow: str,
    env: str, env_note: str, env_mode: str,
    model: str, aspect: str, res: str, seed: str,
    base_image_path: Path,
    scene_image_path: Optional[Path],
    preserve_camera_from_base: bool = False,
    strict_in_place_recolor: bool = False,
    keep_source_scene: bool = False,
    extra_reference_paths: Optional[list[Path]] = None,
    lock_to_reference: bool = False,
    bedding_description: str = "",
    # New structured camera fields. When `shot` is empty, the old `cam`
    # preset is used as a fallback (back-compat with older form posts and
    # the batch / photoshoot paths that haven't been migrated yet).
    shot: str = "",
    yaw: str = "",
    height: str = "",
    dof: str = "",
    detail_region: str = "",
) -> GenerationRequest:
    """
    Translate a parsed FormData payload into a GenerationRequest.
    Shared by /api/generate (single render) and /api/generate-set (color batch).
    Resolves legacy Polish strings via the alias tables so stale browser caches
    keep working.
    """
    upholstery_color = (
        color_custom.strip()
        if color == "custom" and color_custom.strip()
        else _COLOR_PL_TO_EN.get(color, "neutral")
    )
    upholstery_material = _MATERIAL_PL_TO_EN.get(mat, "fabric")
    if mat and mat not in _MATERIAL_PL_TO_EN:
        # Stale browser cache or a hand-rolled request: we silently fell back to
        # a bare "fabric" with no texture spec, which renders an arbitrary
        # weave. Loud in the log so it stops looking like a model problem.
        logger.warning(
            "Unknown material id %r — falling back to generic 'fabric' with no "
            "texture spec. Known ids: %s", mat, ", ".join(_MATERIAL_PL_TO_EN),
        )

    # Texture spec: the fabric's matrix description ALWAYS goes in, and the
    # user's own note is appended as a refinement on top of it. It used to be
    # `notes or spec` — any typed note silently dropped the whole matrix spec.
    texture_spec = " ".join(
        part for part in (_MATERIAL_TEXTURE_EN.get(mat, ""), mat_notes.strip()) if part
    )

    is_bed = kind == "bed"
    sofa_config = (_BED_CONFIG if is_bed else _SOFA_CONFIG).get(size, "3-seater")

    # ---- Resolve structured camera fields ---------------------------- #
    # If the new `shot` field is missing, derive shot/yaw/height from the
    # legacy `cam` preset. The new UI sends both `cam` (preset) and the
    # structured fields explicitly so users can override the preset.
    preset_shot, preset_yaw, preset_height = _CAM_PRESET_TO_STRUCTURED.get(
        cam, ("hero", "34_left", "eye")
    )
    shot_id   = shot.strip()   or preset_shot
    yaw_id    = yaw.strip()    or preset_yaw
    height_id = height.strip() or preset_height
    dof_id    = dof.strip()    or ("macro_shallow" if shot_id.startswith("detail_") else "standard")

    is_detail = shot_id in ("detail_fabric", "detail_corner")
    is_close_up = shot_id == "close_up"
    # Detail shots force a macro lens unless the user explicitly picked one
    # of the longer focal lengths. A 35 mm wide on a detail crop produces a
    # weirdly perspective-distorted macro that doesn't read as a real shot.
    if is_detail and lens.strip() in ("", "35mm_wide", "50mm_natural"):
        lens = "100mm_macro"

    camera_angle, deg = _YAW_TO_ANGLE.get(yaw_id, ("front-34-left", 35))

    # Build framing string from shot type + (optional) region.
    # Region selection rules:
    #   detail_fabric  → DETAIL_REGIONS_FABRIC  (default: weave)
    #   detail_corner  → DETAIL_REGIONS_CORNER  (default: arm_back_corner)
    #   close_up + bed → CLOSE_REGIONS_BED      (default: bed_corner_head)
    #   close_up + sofa→ CLOSE_REGIONS_SOFA     (default: sofa_corner)
    #   other          → no region
    if is_detail:
        default_region = (
            _DETAIL_REGION_DEFAULT_FABRIC if shot_id == "detail_fabric"
            else _DETAIL_REGION_DEFAULT_CORNER
        )
        region_id = detail_region.strip() or default_region
        region_phrase = _DETAIL_REGION_TO_PHRASE.get(
            region_id, _DETAIL_REGION_TO_PHRASE[default_region]
        )
    elif is_close_up:
        default_region = _CLOSE_REGION_DEFAULT_BED if is_bed else _CLOSE_REGION_DEFAULT_SOFA
        region_id = detail_region.strip() or default_region
        # Guard against cross-product region pick (e.g. sofa region with bed
        # product, or vice versa) by falling back to the product's default.
        valid_prefix = "bed_" if is_bed else "sofa_"
        if not region_id.startswith(valid_prefix):
            region_id = default_region
        region_phrase = _DETAIL_REGION_TO_PHRASE.get(
            region_id, _DETAIL_REGION_TO_PHRASE[default_region]
        )
    else:
        region_phrase = ""
    framing_template = _SHOT_TYPE_TO_FRAMING.get(shot_id, _SHOT_TYPE_TO_FRAMING["hero"])
    framing_str = framing_template.format(region=region_phrase) if "{region}" in framing_template else framing_template
    # Append camera-height phrase for non-detail shots (at macro distance
    # height isn't visually relevant — the crop fills the frame regardless).
    if not is_detail:
        height_phrase = _HEIGHT_TO_PHRASE.get(height_id, "")
        if height_phrase:
            framing_str = f"{framing_str}; {height_phrase}"

    aperture_str = _DOF_TO_APERTURE.get(dof_id, "f/4.5")

    lens_id   = _resolve_id(lens,   _LENS_LEGACY_ALIAS)
    tod_id    = _resolve_id(tod,    _TOD_LEGACY_ALIAS)
    shadow_id = _resolve_id(shadow, _SHADOW_LEGACY_ALIAS)

    lens_data       = _LENS_TO_PROMPT.get(lens_id, _LENS_DEFAULT)
    shadow_data     = _SHADOW_TO_PROMPT.get(shadow_id, _SHADOW_DEFAULT)
    tod_description = _TOD_TO_PROMPT.get(tod_id, "")
    env_mode_label, env_description = _ENV_TO_SCENE.get(env, ("packshot", "neutral grey studio backdrop"))

    res_token = (res or "1K").split(" ")[0].strip().upper()
    resolution = res_token if res_token in ("1K", "2K", "4K") else "1K"

    leg_count = 0 if is_bed and legs == "keep" else 4
    leg_id = _LEG_TO_ID.get(legs)

    notes_parts = []
    if env_note.strip(): notes_parts.append(f"environment note: {env_note.strip()}")
    if env_mode.strip(): notes_parts.append(f"environment use: {env_mode.strip()}")
    if seed.strip():     notes_parts.append(f"seed hint: {seed.strip()}")

    return GenerationRequest(
        model_id=model,
        base_product_image=str(base_image_path),
        scene_reference_image=str(scene_image_path) if scene_image_path else None,
        extra_reference_images=[str(p) for p in (extra_reference_paths or [])],
        lock_to_reference=lock_to_reference,
        product_type="bed" if is_bed else "sofa",
        sofa_configuration=sofa_config,
        leg_count=leg_count,
        preserve_list=["frame_silhouette", "stitching"],
        upholstery_color=upholstery_color,
        upholstery_material=upholstery_material,
        texture_notes=texture_spec,
        leg_id=leg_id,
        camera_angle=camera_angle,
        angle_degrees_from_left=deg,
        shadow_direction=shadow_data["direction"],
        focal_length_mm=lens_data["focal_mm"],
        aperture=aperture_str,
        framing=framing_str,
        shot_type=shot_id,
        detail_region_phrase=region_phrase,
        lens_descriptor=lens_data["descriptor"],
        tod_description=tod_description,
        shadow_description=shadow_data["desc"],
        env_mode=env_mode_label,
        env_description=env_description,
        preserve_camera_from_base=preserve_camera_from_base,
        strict_in_place_recolor=strict_in_place_recolor,
        keep_source_scene=keep_source_scene,
        bedding_description=bedding_description.strip(),
        aspect_ratio=aspect,
        resolution=resolution,
        notes=" | ".join(notes_parts),
        api_key=api_key.strip(),
    )


def _recolor_request(
    *, api_key, kind, color, color_custom, mat, mat_notes, size, legs, cam, lens,
    tod, shadow, shot, yaw, height, dof, detail_region, model, aspect, res, seed,
    bedding_desc, source_path,
):
    """One in-place recolor of `source_path`: keep its EXACT angle + background,
    change ONLY the upholstery colour/material. Drives the generator's
    keep_source_scene recolor mode — base image only (no scene reference), and the
    SCENE backdrop block is suppressed so the source's own background is preserved.
    This is the consistency fix for the old flow's colour-miss + background-drift."""
    return _build_generation_request(
        api_key=api_key, kind=kind,
        color=color, color_custom=color_custom,
        mat=mat, mat_notes=mat_notes,
        size=size, legs=legs, cam=cam,
        lens=lens, tod=tod, shadow=shadow,
        shot=shot, yaw=yaw, height=height, dof=dof, detail_region=detail_region,
        env="", env_note="", env_mode="",
        model=model, aspect=aspect, res=res, seed=seed,
        base_image_path=source_path,
        scene_image_path=None,                  # NO scene ref → model can't copy the old colour
        preserve_camera_from_base=True,
        strict_in_place_recolor=True,
        keep_source_scene=True,                 # keep the source photo's own background
        bedding_description=bedding_desc,
    )
