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
