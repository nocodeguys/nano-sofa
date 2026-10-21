"""Phase 3 — one background concept.

The diagnosis found fifteen inputs that could touch the backdrop and no
way to tell which one won. After phase 3 there are three: a backdrop id,
a scene id, or "custom" with the user's photo (plus the explicit "previous
render as scene" flag). These tests pin that contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "app-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "app-v2"))

from app.core.generator import _build_prompt_text  # noqa: E402
from studio.catalog import (  # noqa: E402
    BACKDROPS,
    SCENES,
    background_treatment,
    canonical_background_id,
    resolve_background,
)
from studio.normalize import PROFILES, resolve_profile  # noqa: E402


def _req(server, base_image, **over):
    kwargs = dict(
        api_key="k", kind="bed", color="taupe", color_custom="", mat="cremona", mat_notes="",
        size="160", legs="keep", cam="studio", lens="35mm_wide", tod="golden_hour",
        shadow="hard_studio_5", env="", env_note="", env_mode="",
        model="gemini-nano-banana-2.1", aspect="4:3", res="1K", seed="",
        base_image_path=base_image, scene_image_path=None,
    )
    kwargs.update(over)
    return server._build_generation_request(**kwargs)


# --------------------------------------------------------------------------
# catalog.json is the one table
# --------------------------------------------------------------------------
def test_every_backdrop_has_prompt_hex_and_consistent_normalize_tones():
    for b in BACKDROPS.values():
        assert b["prompt_en"].strip(), b["id"]
        if b.get("normalize"):
            assert b["id"] in PROFILES, b["id"]
            assert b["hex"].upper() in b["prompt_en"].upper(), b["id"]
            # Flat backdrops: the card hex IS the normalize baseline tone. A
            # two-axis gradient (four corner tones) names its key-light corner
            # instead, so only the flat ones are compared.
            if not b["normalize"].get("top_left_rgb"):
                r, g, bl = PROFILES[b["id"]].background
                assert b["hex"].upper() == f"#{r:02X}{g:02X}{bl:02X}", (
                    f"{b['id']}: hex {b['hex']} vs normalize background {(r, g, bl)}"
                )
        if b.get("plate"):
            assert (REPO_ROOT / "app-v2" / "scene-references" / b["plate"]).is_file(), b["plate"]


def test_old_env_ids_resolve_through_aliases():
    assert canonical_background_id("cyclorama_architectural") == "ivory"
    assert canonical_background_id("studio_white") == "warm"
    assert canonical_background_id("cyclorama_transparent") == "transparent"
    assert canonical_background_id("scandi") == "scandi"
    assert canonical_background_id("custom") == "custom"
    assert canonical_background_id("nie-ma-takiego") == ""
    assert resolve_background("nie-ma-takiego")[1]["id"] == "ivory"


def test_treatment_is_decided_by_the_backdrop_entry():
    t = background_treatment("ivory")
    assert t["kind"] == "backdrop" and t["locked"] and t["normalize_profile"] == "ivory"
    assert t["plate"] == "cyclorama_architectural.png" and not t["transparent"]
    t = background_treatment("grey")
    assert t["kind"] == "backdrop" and not t["locked"] and t["normalize_profile"] is None
    t = background_treatment("transparent")
    assert t["transparent"] and not t["locked"]
    t = background_treatment("scandi")
    assert t["kind"] == "scene" and not t["locked"] and t["normalize_profile"] is None
    t = background_treatment("custom")
    assert t["kind"] == "custom" and not t["locked"]
    assert background_treatment("")["id"] == "ivory"


# --------------------------------------------------------------------------
# The request builder: one id in, the right prompt out
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bg", sorted(BACKDROPS))
def test_backdrop_reaches_the_prompt(server, base_image, bg):
    req = _req(server, base_image, background=bg)
    entry = BACKDROPS[bg]
    assert req.env_mode == "packshot"
    assert req.env_description == entry["prompt_en"]
    assert entry["prompt_en"][:60] in _build_prompt_text(req)
    if entry.get("locks"):
        # Phase 4: the backdrop locks the LIGHT only; the posted camera wins.
        assert "golden" not in req.tod_description.lower()
        assert "hard" not in req.shadow_description.lower()
        assert req.focal_length_mm == 35            # the caller's lens survives
        assert req.catalog_framing_contract        # hero → numeric contract
        assert (Path(req.scene_reference_image).name == entry["plate"]) if entry.get("plate") \
            else req.scene_reference_image is None
        # An older client that posts no camera gets the backdrop's defaults.
        old = _req(server, base_image, background=bg, lens="", dof="", height="", shot="")
        assert old.focal_length_mm == 85 and old.aperture == "f/8.0" and old.shot_type == "hero"
    else:
        assert req.focal_length_mm == 35            # the caller's lens survives
        assert "golden" in req.tod_description.lower()
        assert not req.catalog_framing_contract


@pytest.mark.parametrize("scene", sorted(SCENES))
def test_scene_reaches_the_prompt(server, base_image, scene):
    req = _req(server, base_image, background=scene)
    assert req.env_mode == "lifestyle"
    assert req.env_description == SCENES[scene]["prompt_en"]
    assert "SCENE (lifestyle)" in _build_prompt_text(req)
    assert not req.catalog_framing_contract and req.focal_length_mm == 35


def test_custom_background_keeps_the_photo_and_the_note(server, base_image):
    req = _req(server, base_image, background="custom", scene_image_path=base_image,
               env_note="salon na poddaszu")
    assert req.env_mode == "lifestyle"
    assert req.scene_reference_image == str(base_image)
    assert "salon na poddaszu" in req.notes
    text = _build_prompt_text(req)
    assert "within the scene shown in image 2" in text


def test_note_and_stale_upload_do_not_leak_into_other_backgrounds(server, base_image):
    """Before phase 3 a note and an upload made under "custom" rode along
    with every other env. Now the note belongs to "custom" only, and a
    locked backdrop replaces any caller scene with its own plate."""
    scene = _req(server, base_image, background="scandi", env_note="salon na poddaszu")
    assert "salon na poddaszu" not in scene.notes
    locked = _req(server, base_image, background="ivory", scene_image_path=base_image,
                  env_note="salon na poddaszu")
    assert Path(locked.scene_reference_image).name == "cyclorama_architectural.png"
    assert "salon na poddaszu" not in locked.notes


def test_legacy_catalog_and_env_fields_map_onto_background(server, base_image):
    old_catalog = _req(server, base_image, catalog=True, catalog_profile="softblush")
    new = _req(server, base_image, background="softblush")
    assert old_catalog.env_description == new.env_description
    assert old_catalog.scene_reference_image == new.scene_reference_image
    old_env = _req(server, base_image, env="cyclorama_grey")
    assert old_env.env_description == BACKDROPS["grey"]["prompt_en"]
    assert resolve_profile("cyclorama_softblush").name == "softblush"


@pytest.mark.parametrize("shot", ["wide", "three_quarter", "cropped", "close_up", "detail_fabric", "detail_corner"])
def test_only_hero_gets_the_framing_contract(server, base_image, shot):
    req = _req(server, base_image, background="ivory", shot=shot)
    assert req.shot_type == shot
    assert not req.catalog_framing_contract
    assert _req(server, base_image, background="ivory", shot="hero").catalog_framing_contract


def test_close_up_is_a_tight_shot(server, base_image):
    """A close-up drops the plate and the in-use photo like a macro does, and
    its SCENE / CAMERA say the full product is not in the frame."""
    from app.core.generator import plan_reference_slots
    req = _req(server, base_image, background="ivory", shot="close_up")
    roles = [s.role for s in plan_reference_slots(req, 14)]
    assert "scene" not in roles and "material_application" not in roles
    text = _build_prompt_text(req)
    assert "CAMERA — CLOSE-UP CROP" in text and "SCENE (close-up crop)" in text
    assert "SOURCE BACKGROUND DISCARD" not in text
    assert "must NOT be visible" in text


# --------------------------------------------------------------------------
# Routes: the upload is accepted only where it means something
# --------------------------------------------------------------------------
@pytest.fixture()
def capture_render(server, monkeypatch, base_image):
    """Capture the request the route hands to the engine; return a fake success."""
    from PIL import Image
    from app.core.generator import GenerationResult
    from studio import routes_generate

    seen = {}

    def fake_render(req, openai_key="", quality="", openrouter_key=""):
        seen["req"] = req
        out = Path(base_image).parent / "render.png"
        Image.new("RGB", (64, 48), (200, 190, 180)).save(out)
        return GenerationResult(
            success=True, generation_id="g1", output_path=out, output_image=Image.open(out),
            next_history=[], actual_cost=0.01, attempts=1, error_message=None,
            model_id=req.model_id, resolution="1K",
        )

    monkeypatch.setattr(routes_generate, "_render_product", fake_render)
    monkeypatch.setattr(routes_generate, "normalize_packshot", lambda path, profile: (path, False))
    return seen


def _post(client, base_image, **fields):
    data = {"api_key": "AIza-test", "kind": "bed", "mat": "cremona", "color": "taupe", "size": "160"}
    data.update({k: v for k, v in fields.items() if k != "scene"})
    files = {"base_image": ("base.png", base_image.read_bytes(), "image/png")}
    if fields.get("scene"):
        files["scene_image"] = ("scene.png", base_image.read_bytes(), "image/png")
    return client.post("/api/generate", data=data, files=files)


def test_route_drops_scene_upload_next_to_a_studio_backdrop(server, base_image, capture_render):
    from fastapi.testclient import TestClient
    client = TestClient(server.app)
    r = _post(client, base_image, background="grey", scene=True)
    assert r.status_code == 200, r.text
    assert capture_render["req"].scene_reference_image is None
    assert r.json()["background"] == "grey"


def test_route_keeps_scene_upload_for_custom_and_for_previous_render(server, base_image, capture_render):
    from fastapi.testclient import TestClient
    client = TestClient(server.app)
    r = _post(client, base_image, background="custom", scene=True)
    assert r.status_code == 200, r.text
    req = capture_render["req"]
    assert req.scene_reference_image is not None and not req.scene_contains_product

    r = _post(client, base_image, background="scandi", scene=True, scene_from_render="1")
    assert r.status_code == 200, r.text
    req = capture_render["req"]
    assert req.scene_reference_image is not None and req.scene_contains_product
    assert "DIFFERENT upholstery colour" in _build_prompt_text(req)
