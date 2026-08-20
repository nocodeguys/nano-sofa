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
