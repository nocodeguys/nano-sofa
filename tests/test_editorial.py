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


def test_openrouter_aspect_clamping(server):
    from studio.openrouter import _clamp_aspect
    assert _clamp_aspect("krea/krea-2-large", "3:4") == "2:3"
    assert _clamp_aspect("krea/krea-2-large", "21:9") == "16:9"
    assert _clamp_aspect("krea/krea-2-large", "16:9") == "16:9"
    assert _clamp_aspect("bytedance-seed/seedream-5-0-pro", "3:4") == "3:4"


def test_generate_free_openrouter_requires_or_key(client):
    r = client.post("/api/generate-free", data={
        "api_key": "x", "prompt": "cokolwiek",
        "model": "black-forest-labs/flux.2-pro",
    })
    assert r.json()["error_code"] == "MISSING_OPENROUTER_KEY"
