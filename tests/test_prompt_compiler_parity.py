"""Phase 2a parity: the new compiler (app/core/prompt) must emit exactly the
text the old builders emitted, for every branch — not just the 28 goldens.

tests/legacy_prompt_builder.py is a frozen copy of the old code. This test
walks a grid of requests through both and asserts byte equality. When
phase 2b changes the wording on purpose, delete the legacy module and this
test together; the goldens take over from there.
"""
from __future__ import annotations

import itertools
import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
for p in (REPO_ROOT, REPO_ROOT / "app-v2", REPO_ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.core.generator import (  # noqa: E402
    GenerationRequest,
    _build_prompt_text,
    _build_scene_block,
    plan_reference_slots,
    slot_numbers,
)
from studio.catalog import _MATERIAL_NEGATIVES_EN  # noqa: E402
from studio.mappings import _build_freeform_prompt  # noqa: E402

import legacy_prompt_builder as legacy  # noqa: E402


# --------------------------------------------------------------------------
# Product requests through the real builder, over a grid
# --------------------------------------------------------------------------
def _req(server, base_image, **over):
    kwargs = dict(
        api_key="k", kind="bed", color="taupe", color_custom="", mat="cremona", mat_notes="",
        size="160", legs="keep", cam="studio", lens="50mm_natural", tod="noon_neutral",
        shadow="soft_diffuse", env="scandi", env_note="", env_mode="reference",
        model="gemini-nano-banana-2.1", aspect="4:3", res="1K", seed="",
        base_image_path=base_image, scene_image_path=None,
    )
    kwargs.update(over)
    return server._build_generation_request(**kwargs)


GRID = list(itertools.product(
    ("bed", "sofa"),
    ("catalog", "scandi", "cyclorama_warm", "transparent", "custom"),
    ("hero", "close_up", "detail_fabric", "wide"),
    (False, True),                       # preserve camera from base
))


@pytest.mark.parametrize("kind,env,shot,preserve", GRID,
                         ids=[f"{k}-{e}-{s}-{'pres' if p else 'free'}" for k, e, s, p in GRID])
def test_product_prompt_parity(server, base_image, kind, env, shot, preserve):
    mat, color, size = ("cremona", "taupe", "160") if kind == "bed" else ("boucle", "forest", "3")
    catalog = env == "catalog"
    req = _req(
        server, base_image, kind=kind, mat=mat, color=color, size=size, shot=shot,
        env="" if catalog else env, catalog=catalog, catalog_profile="ivory" if catalog else "",
        preserve_camera_from_base=preserve,
        scene_image_path=base_image if env == "custom" else None,
        bedding_description="crisp white linen" if kind == "bed" else "",
    )
    slots = slot_numbers(plan_reference_slots(req))
    assert _build_prompt_text(req, slots) == legacy._build_prompt_text(req, slots)
    assert _build_scene_block(req, "bed" if kind == "bed" else "sofa", slots) == \
        legacy._build_scene_block(req, "bed" if kind == "bed" else "sofa", slots)


def test_product_prompt_parity_special_paths(server, base_image):
    """Branches the wizard grid does not reach: in-place recolour, reference
    lock, moodboards, scene-with-product, view consistency, leg swap with
    descriptor, legacy env_mode, notes, non-texture-only swatch, custom hex."""
    base = _req(server, base_image, color_custom="#2E3B2C", color="")
    variants = [
        replace(base, strict_in_place_recolor=True, preserve_camera_from_base=True,
                keep_source_scene=True),
        replace(base, strict_in_place_recolor=True, preserve_camera_from_base=True,
                env_mode="packshot"),
        replace(base, lock_to_reference=True, extra_reference_images=[str(base_image)]),
        replace(base, extra_reference_images=[str(base_image), str(base_image)]),
        replace(base, scene_reference_image=str(base_image), scene_contains_product=True),
        replace(base, scene_reference_image=str(base_image), scene_contains_product=True,
                env_mode="packshot", env_description="warm ivory cyclorama"),
        replace(base, scene_reference_image=str(base_image), view_consistency=True),
        replace(base, leg_id="tapered-wood", leg_explicit_descriptor="tapered oak legs", leg_count=4),
        replace(base, leg_id="tapered-wood", leg_count=0),
        replace(base, env_mode="", shadow_direction="4 o-clock", leg_count=4),
        replace(base, env_mode="", scene_reference_image=str(base_image)),
        replace(base, notes="environment note: low sun"),
        replace(base, use_swatch_for_fabric=True, swatch_texture_only=False),
        replace(base, use_swatch_for_fabric=True, swatch_texture_only=True),
        replace(base, product_type="sofa", leg_count=4, preserve_list=["frame_silhouette"]),
        replace(base, product_type="bed", frame_style="panel-bed"),
        replace(base, preserve_list=[]),
        replace(base, negative_list=[]),
        replace(base, texture_notes=""),
        replace(base, shot_type="detail_corner", env_mode="packshot",
                scene_reference_image=str(base_image)),
        replace(base, shot_type="detail_fabric", env_mode="lifestyle"),
    ]
    for i, req in enumerate(variants):
        slots = slot_numbers(plan_reference_slots(req))
        assert _build_prompt_text(req, slots) == legacy._build_prompt_text(req, slots), f"variant {i}"
        # And with the slot map derived inside (the tests' calling convention).
        assert _build_prompt_text(req) == legacy._build_prompt_text(req), f"variant {i} (auto slots)"


# --------------------------------------------------------------------------
# Freeform prompts over a grid of pickers
# --------------------------------------------------------------------------
FREE_GRID = list(itertools.product(
    ("magazine_cover", "", "nope"),
    ("japandi", "", "custom"),
    ("golden_hour", ""),
    ("85mm_product", ""),
    ("low", ""),
    ("forest", ""),
    ("boucle", ""),
    ("silhouette", ""),
    ("", "42"),
))


@pytest.mark.parametrize("style,env,tod,lens,height,color,mat,people,seed", FREE_GRID)
def test_freeform_prompt_parity(server, style, env, tod, lens, height, color, mat, people, seed):
    kw = dict(
        text="Przytulna sypialnia o świcie.", style=style, env=env, tod=tod, lens=lens,
        height=height,
        color_en=server._COLOR_PL_TO_EN.get(color, ""),
        mat_noun_en=server._MATERIAL_PL_TO_EN.get(mat, ""),
        mat_texture_en=server._MATERIAL_TEXTURE_EN.get(mat, ""),
        mat_avoid_en=list(_MATERIAL_NEGATIVES_EN.get(mat, [])) if mat else [],
        people=people, seed=seed,
        color_hex="#2E3B2C" if color else "",
    )
    for slots in (
        {},
        {"material_macro": 1, "color_patch": 2},
        {"material_macro": 1, "color_patch": 2, "material_left": 3, "material_right": 4,
         "material_behavior": 5, "material_application": 6, "extra_reference_1": 7,
         "extra_reference_2": 8},
        {"material_left": 1, "extra_reference_1": 2},
    ):
        assert _build_freeform_prompt(slots=slots, **kw) == legacy._build_freeform_prompt(slots=slots, **kw)
