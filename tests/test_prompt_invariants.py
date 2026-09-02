"""Prompt-assembly invariants — regression guards for the fabric-spec bugs.

The hard-won rules (see ARCHITECTURE.md):
  1. Every material's rich texture spec must survive into the final prompt.
  2. User-typed material notes must ADD to the spec, not silently replace it
     (the "note drops the spec" bug fixed for plecionka in a794761).
  3. The English material noun must be the catalog's noun (which is kept in
     agreement with the spec — e.g. "woven textured chenille fabric", never
     the bare stereotype noun).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.generator import _build_prompt_text

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = json.loads((REPO_ROOT / "app-v2" / "catalog.json").read_text())
MATERIAL_IDS = [m["id"] for m in CATALOG["materials"]]


def _request(server, base_image, *, mat: str, mat_notes: str = ""):
    return server._build_generation_request(
        api_key="test-key",
        kind="sofa",
        color="greige", color_custom="",
        mat=mat, mat_notes=mat_notes,
        size="3",
        legs="keep",
        cam="studio",
        lens="50mm_natural", tod="noon_neutral", shadow="soft_diffuse",
        env="cyclorama_neutral", env_note="", env_mode="",
        model="gemini-2.5-flash-image", aspect="4:3", res="1K", seed="",
        base_image_path=base_image,
        scene_image_path=None,
    )


def _distinctive_fragment(texture_spec: str) -> str:
    """First sentence of the spec — long enough to be unmistakable."""
    return texture_spec.split(".")[0].strip()


@pytest.mark.parametrize("mat", MATERIAL_IDS)
def test_texture_spec_survives_into_prompt(server, base_image, mat):
    req = _request(server, base_image, mat=mat)
    prompt = _build_prompt_text(req)
    fragment = _distinctive_fragment(server._MATERIAL_TEXTURE_EN[mat])
    assert fragment in prompt, (
        f"texture spec for {mat!r} missing from the final prompt"
    )


@pytest.mark.parametrize("mat", MATERIAL_IDS)
def test_material_noun_matches_catalog(server, base_image, mat):
    req = _request(server, base_image, mat=mat)
    prompt = _build_prompt_text(req)
    assert server._MATERIAL_PL_TO_EN[mat] in prompt, (
        f"catalog noun for {mat!r} missing from the final prompt"
    )


def test_user_notes_do_not_drop_texture_spec(server, base_image):
    """The a794761 regression: typing a note must not cancel the spec."""
    note = "with extra decorative topstitching"
    req = _request(server, base_image, mat="chenille", mat_notes=note)
    prompt = _build_prompt_text(req)
    fragment = _distinctive_fragment(server._MATERIAL_TEXTURE_EN["chenille"])
    assert fragment in prompt, "user note displaced the texture spec"
    assert note in prompt, "user note itself missing from the prompt"


def test_boucle_prompt_disambiguates_real_loops_from_teddy_and_foam(
    server, base_image
):
    req = _request(server, base_image, mat="boucle")
    prompt = _build_prompt_text(req)

    assert "irregular open and closed yarn loops" in prompt
    assert "tiny darker cavities between the loops" in prompt
    assert "teddy or sherpa fleece" in prompt
    assert "uniform pebbled foam" in prompt


def test_cremona_prompt_preserves_the_irregular_reference_character(server, base_image):
    req = _request(server, base_image, mat="cremona")
    prompt = _build_prompt_text(req)

    assert "only a few millimetres across" in prompt
    assert "many dozens span a cushion" in prompt
    assert "subtle anisotropic response" in prompt
    assert "calm, continuous and finely tactile" in prompt
    assert "local, soft-edged and low-contrast" in prompt
    assert "never form broad panel-scale clouds" in prompt
    assert "leopard, dalmatian or polka-dot spots" in prompt
    assert "broad panel-scale cloudy blotches" in prompt
    assert "crushed velvet marbling" in prompt
    assert "crisp high-frequency separation" in prompt
    assert "dark micro-occlusion and tiny contact shadows" in prompt
    assert "delicate fuzzy halo" in prompt
    assert "sparse, narrow satin micro-highlights" in prompt
    assert "generic flat linen weave" in prompt
    assert "foam or sponge texture" in prompt
    assert "regular grid or checkerboard" in prompt
    assert "repeating rectangular cells" in prompt
    assert "open loop bouclé" in prompt
    assert "flat printed grid" in prompt
    assert "physical-sample photographs are the absolute authority" in prompt


def test_catalog_ids_match_schema_enum(server):
    """catalog.json and prompts/schemas/sofa.json must agree on material ids."""
    schema = json.loads(
        (REPO_ROOT / "prompts" / "schemas" / "sofa.json").read_text()
    )
    enum = set(
        schema["properties"]["variant"]["properties"]["upholstery"]
        ["properties"]["material"]["enum"]
    )
    assert set(MATERIAL_IDS) <= enum, (
        f"materials missing from schema enum: {set(MATERIAL_IDS) - enum}"
    )


def test_catalog_light_source_is_explicitly_outside_the_frame(server, base_image):
    req = server._build_generation_request(
        api_key="test-key", kind="bed",
        color="greige", color_custom="", mat="boucle", mat_notes="",
        size="160", legs="keep", cam="studio",
        lens="50mm_natural", tod="noon_neutral", shadow="soft_diffuse",
        env="cyclorama_warm", env_note="", env_mode="",
        model="gemini-3.1-flash-image", aspect="4:3", res="2K", seed="",
        base_image_path=base_image, scene_image_path=None,
        catalog=True, catalog_profile="ivory",
    )
    prompt = _build_prompt_text(req)
    assert "OUTSIDE the image bounds" in prompt
    assert "must remain completely off-camera" in prompt
    assert "soft-box key light positioned at the TOP-LEFT" not in prompt
