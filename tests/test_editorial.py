"""Editorial (freeform) mode — prompt composition + endpoint validation."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.generator import _build_prompt_text, validate_request

BRIEF = "Przytulna sypialnia o świcie, łóżko z baldachimem, poranna mgła."


def _freeform(server, **kw):
    args = dict(
        api_key="test-key", text=BRIEF,
        style="magazine_cover", env="japandi", tod="golden_hour",
        lens="85mm_product", height="low", color="forest", mat="boucle",
        model="gemini-2.5-flash-image", aspect="3:4", res="1K", seed="",
    )
    args.update(kw)
    return server._build_freeform_request(**args)


def test_freeform_prompt_composition(server):
    req = _freeform(server)
    prompt = _build_prompt_text(req)
    assert BRIEF in prompt, "user brief missing"
    assert "masthead" in prompt, "magazine-cover art direction missing"
    assert "japandi" in prompt, "scene fragment missing"
    assert "golden-hour" in prompt, "light fragment missing"
    assert "85 mm short telephoto" in prompt, "lens fragment missing"
    assert server._COLOR_PL_TO_EN["forest"] in prompt, "palette fragment missing"
    assert server._MATERIAL_PL_TO_EN["boucle"] in prompt, "fabric cue missing"
    # No variant-pipeline blocks may leak into a freeform prompt.
    assert "PRESERVE" not in prompt
    assert "BED SIZE" not in prompt


def test_freeform_pickers_are_optional(server):
    req = _freeform(server, style="", env="", tod="", lens="", height="",
                    color="", mat="")
    prompt = _build_prompt_text(req)
    assert BRIEF in prompt
    assert "ART DIRECTION" not in prompt
    assert "SETTING" not in prompt
    assert "OUTPUT STYLE" in prompt


def test_freeform_passes_validation_without_base_image(server):
    req = _freeform(server)
    errors = validate_request(req)
    assert not any("base product image" in e for e in errors), errors


@pytest.fixture(scope="module")
def client(server):
    return TestClient(server.app)


def test_editorial_page_served(client):
    r = client.get("/editorial")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_generate_free_requires_key_and_prompt(client):
    r = client.post("/api/generate-free", data={"prompt": "cokolwiek"})
    assert r.json()["error_code"] == "MISSING_API_KEY"
    r = client.post("/api/generate-free", data={"api_key": "x", "prompt": ""})
    assert r.json()["error_code"] == "MISSING_PROMPT"


def test_fabric_cue_is_hard_constraint_with_full_spec(server):
    """The one-line hint got ignored by the model — the full texture spec and
    the hard-constraint framing must both land in the prompt."""
    req = _freeform(server, mat="chenille")
    prompt = _build_prompt_text(req)
    assert "TEXTILE DIRECTION (hard constraint)" in prompt
    # a sentence from deep inside the spec — proves the WHOLE spec is there
    assert "Highlights stay broad, diffuse and matte" in prompt


def test_people_default_is_explicit_negative(server):
    prompt = _build_prompt_text(_freeform(server))
    assert "No people, no human figures" in prompt


def test_people_option_replaces_negative(server):
    prompt = _build_prompt_text(_freeform(server, people="lifestyle"))
    assert "PEOPLE:" in prompt
    assert "interacts naturally" in prompt
    assert "No people, no human figures" not in prompt


def test_config_lists_editorial_models(client):
    cfg = client.get("/api/config").json()
    ed = cfg.get("editorial_models") or []
    providers = {m["id"]: m.get("provider") for m in ed}
    for slug in (
        "openai/gpt-image-2",
        "openai/gpt-image-1",
        "openai/gpt-image-1-mini",
        "black-forest-labs/flux.2-pro",
        "bytedance-seed/seedream-4.5",
        "bytedance-seed/seedream-5-0-pro",
        "bytedance-seed/seedream-5-0-lite",
        "krea/krea-2-large",
        "krea/krea-2-medium",
    ):
        assert providers.get(slug) == "openrouter", f"{slug} missing"
    assert any(p == "google" for p in providers.values())
    # Krea's reduced vocabulary must reach the frontend so it can disable chips.
    krea = next(m for m in ed if m["id"] == "krea/krea-2-large")
    assert "3:4" not in krea["aspects"]
    assert krea["max_refs"] == 1
    assert krea["moodboard_max"] == 1
    # GPT Image 2 via OpenRouter: 16 references, every aspect, a quality tier.
    gpt2 = next(m for m in ed if m["id"] == "openai/gpt-image-2")
    assert gpt2["max_refs"] == 16
    assert gpt2["moodboard_max"] == 6
    assert {"3:4", "21:9", "16:9"} <= set(gpt2["aspects"])
    assert gpt2["qualities"] == ["low", "medium", "high"]
    assert gpt2["default_quality"] == "high"
    # Gemini keeps its three moodboards and has no quality tiers.
    google = next(m for m in ed if m["provider"] == "google")
    assert google["moodboard_max"] == 3 and google["qualities"] == []
    # GPT Image 2.5 direct is offered in Editorial too (OpenAI key).
    assert providers.get("gpt-image-2.5-flare") == "openai"
    assert providers.get("gpt-image-2.5-sunburst") == "openai"


def test_config_lists_lab_models(client):
    cfg = client.get("/api/config").json()
    lab = cfg.get("lab_models") or []
    ids = {m["id"]: m for m in lab}
    assert set(ids) == {"gpt-image-2.5-flare", "gpt-image-2.5-sunburst"}
    assert cfg["lab_default_model"] == "gpt-image-2.5-flare"
    for m in lab:
        assert m["provider"] == "openai"
        assert m["max_refs"] == 16 and m["moodboard_max"] == 6
        assert m["resolutions"] == ["1K", "2K"]
        assert {"xhigh", "max"} <= set(m["qualities"])
        assert m["default_quality"] == "high"
        assert len(m["aspects"]) == 8


def test_openrouter_aspect_clamping(server):
    from studio.openrouter import _clamp_aspect
    assert _clamp_aspect("krea/krea-2-large", "3:4") == "2:3"
    assert _clamp_aspect("krea/krea-2-large", "21:9") == "16:9"
    assert _clamp_aspect("krea/krea-2-large", "16:9") == "16:9"
    assert _clamp_aspect("bytedance-seed/seedream-5-0-pro", "3:4") == "3:4"
    # GPT Image 1 only knows 1:1 / 2:3 / 3:2 — the fallback chain must keep
    # orientation (21:9 → 16:9 → 3:2) instead of collapsing to square.
    assert _clamp_aspect("openai/gpt-image-1", "4:3") == "3:2"
    assert _clamp_aspect("openai/gpt-image-1", "16:9") == "3:2"
    assert _clamp_aspect("openai/gpt-image-1", "21:9") == "3:2"
    assert _clamp_aspect("openai/gpt-image-1", "9:16") == "2:3"
    assert _clamp_aspect("openai/gpt-image-2", "21:9") == "21:9"


def test_generate_free_openrouter_requires_or_key(client):
    r = client.post("/api/generate-free", data={
        "api_key": "x", "prompt": "cokolwiek",
        "model": "black-forest-labs/flux.2-pro",
    })
    assert r.json()["error_code"] == "MISSING_OPENROUTER_KEY"
    r = client.post("/api/generate-free", data={
        "api_key": "x", "prompt": "cokolwiek",
        "model": "openai/gpt-image-2",
    })
    assert r.json()["error_code"] == "MISSING_OPENROUTER_KEY"


def test_generate_free_openai_requires_openai_key(client):
    r = client.post("/api/generate-free", data={
        "api_key": "x", "openrouter_key": "sk-or-x", "prompt": "cokolwiek",
        "model": "gpt-image-2.5-flare",
    })
    assert r.json()["error_code"] == "MISSING_OPENAI_KEY"


def test_lab_page_served(client):
    r = client.get("/lab")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


# --------------------------------------------------------------------------- #
# Freeform reference plan — a picked fabric brings its whole curated set and
# the picked colour its exact patch; the prompt names only attached images.
# --------------------------------------------------------------------------- #

def _roles(req, max_refs=None):
    from app.core.generator import plan_freeform_reference_slots
    return [slot.role for slot in plan_freeform_reference_slots(req, max_refs)]


def test_freeform_declares_material_set_and_colour_patch(server, base_image):
    # cremona has all five curated views on disk; velutto-27 carries a
    # verified hex → six authority references, then the moodboard.
    req = _freeform(server, mat="cremona", color="velutto-27",
                    model="gemini-3.1-flash-image",
                    extra_reference_paths=[base_image])
    assert req.upholstery_hex.upper() == "#122D24"
    assert _roles(req) == [
        "material_macro", "color_patch", "material_left", "material_right",
        "material_behavior", "material_application", "extra_reference_1",
    ]
    prompt = _build_prompt_text(req)
    assert "Attached image 1 is a close-up photograph" in prompt
    assert "Attached image 2 is a flat, evenly lit patch of the exact target upholstery colour #122D24" in prompt
    assert "Attached images 3 and 4 show the same fabric from opposing oblique viewpoints" in prompt
    assert "Attached image 5 shows the same fabric under grazing light" in prompt
    assert "Attached image 6 shows a comparable fabric on a whole furniture piece" in prompt
    assert "Use attached image 7 as loose mood" in prompt


def test_freeform_prompt_names_only_attached_references(server, base_image):
    # Same request on the 3-reference legacy model: the plan is cut to three
    # and the prompt must not describe the dropped images.
    req = _freeform(server, mat="cremona", color="velutto-27",
                    model="gemini-2.5-flash-image",
                    extra_reference_paths=[base_image])
    assert _roles(req) == ["material_macro", "color_patch", "material_left"]
    prompt = _build_prompt_text(req)
    assert "Attached image 3 shows the same fabric from an oblique viewpoint" in prompt
    # The texture spec itself may mention grazing light — assert on the slot
    # sentences, which must be absent for the dropped references.
    assert "shows the same fabric under grazing light" not in prompt
    assert "shows a comparable fabric on a whole furniture piece" not in prompt
    assert "as loose mood and styling" not in prompt
    assert "Attached image 4" not in prompt


def test_freeform_external_cap_overrides_schema(server, base_image):
    # An OpenRouter / OpenAI slug is unknown to the schema (default cap 3);
    # the engine's own cap must win and the prompt follow it.
    req = _freeform(server, mat="cremona", color="velutto-27",
                    model="openai/gpt-image-2",
                    extra_reference_paths=[base_image, base_image],
                    max_refs=16)
    assert len(_roles(req, 16)) == 8
    assert "Use attached images 7–8 as loose mood" in _build_prompt_text(req)
    # Without a fabric or colour, only the moodboards are attached.
    bare = _freeform(server, mat="", color="", extra_reference_paths=[base_image])
    assert _roles(bare) == ["extra_reference_1"]
    assert "Use attached image 1 as loose mood" in _build_prompt_text(bare)
