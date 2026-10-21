"""Meli (Lab): wood-colour recolor of solid-wood beds on OpenRouter models."""
from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture
def client(server):
    return TestClient(server.app)


@pytest.fixture
def meli_data(server, tmp_path, monkeypatch):
    """A temporary palette + finish photographs in place of app-v2/meli."""
    import studio.meli as meli

    refs = tmp_path / "references"
    refs.mkdir()
    palette = tmp_path / "palette.json"
    palette.write_text(json.dumps({"colors": [
        {"id": "dab-miodowy", "name_pl": "Dąb miodowy", "hex": "c49a6c",
         "finish": "stain", "prompt_en": "warm honey oak", "group": "Dąb"},
        {"id": "bialy", "name_pl": "Biały kryjący", "finish": "opaque"},
        {"id": "szary-lazur", "name_pl": "Szary lazur", "opacity": 50},
        {"id": "x", "name_pl": "Zły wpis", "finish": "lakier"},
        {"name_pl": "bez id"},
    ]}), encoding="utf-8")
    for name in ("dab-miodowy.jpg", "dab-miodowy-2.jpg", "dab-miodowy-10.jpg", "dab-miodowy-old.jpg"):
        Image.new("RGB", (32, 32), (196, 154, 108)).save(refs / name)
    monkeypatch.setattr(meli, "_PALETTE_PATH", palette)
    monkeypatch.setattr(meli, "_REFS_DIR", refs)
    return meli


def _png(w=400, h=300) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (150, 110, 70)).save(buf, format="PNG")
    return buf.getvalue()


def test_meli_page_and_config(client, meli_data):
    assert client.get("/meli").status_code == 200
    cfg = client.get("/api/meli/config").json()
    ids = [c["id"] for c in cfg["palette"]]
    assert ids == ["dab-miodowy", "bialy", "szary-lazur", "x"]
    assert [l["value"] for l in cfg["opacity_levels"]] == [10, 30, 55, 80, 100]
    assert cfg["palette"][2]["opacity"] == 55  # snapped to the nearest level
    oak = cfg["palette"][0]
    assert oak["hex"] == "#C49A6C" and oak["finish"] == "stain" and oak["group"] == "Dąb"
    # <id>.jpg first, then numbered extras in numeric order; other suffixes ignored.
    assert [r.rsplit("/", 1)[1] for r in oak["references"]] == [
        "dab-miodowy.jpg", "dab-miodowy-2.jpg", "dab-miodowy-10.jpg",
    ]
    assert cfg["palette"][3]["finish"] == "stain"  # unknown finish falls back
    # Every OpenRouter image model is offered; Nano Banana 2.1 is the default.
    from studio.openrouter import OPENROUTER_MODELS
    assert {m["id"] for m in cfg["models"]} == set(OPENROUTER_MODELS)
    assert cfg["default_model"] == "google/gemini-nano-banana-2.1"
    assert client.get(oak["references"][0]).status_code == 200
    assert client.get("/api/meli/ref/..%2Fpalette.json").status_code == 404


def test_nearest_aspect_keeps_the_photo_frame(server):
    from studio.meli import nearest_aspect
    assert nearest_aspect(4000, 3000, ["1:1", "4:3", "3:2"]) == "4:3"
    assert nearest_aspect(1080, 1920, ["1:1", "9:16", "2:3"]) == "9:16"
    assert nearest_aspect(2000, 1000, ["1:1", "4:3", "16:9"]) == "16:9"


def test_recolor_sends_photo_finish_refs_and_patch(client, meli_data, monkeypatch):
    captured = {}

    def fake_generate(**kw):
        captured.update(kw)
        path = kw["references"][0][1]  # any existing image works as the "render"
        return {"generation_id": "g1", "output_path": path, "cost": 0.05,
                "elapsed_ms": 1200, "model_id": kw["model"], "resolution": "2K", "quality": ""}

    async def fake_derived(master, fmt, quality, transparent):
        return "/api/outputs/x.jpg", "jpg", False

    monkeypatch.setattr(meli_data, "generate_openrouter", fake_generate)
    monkeypatch.setattr(meli_data, "_derived_url", fake_derived)
    r = client.post("/api/meli/recolor", data={
        "openrouter_key": "sk-or-x", "model": "google/gemini-nano-banana-2.1",
        "color": "dab-miodowy", "product_name": "  Meli   160 ", "res": "2K",
    }, files={"base": ("bed.png", _png(), "image/png")})
    data = r.json()
    assert data["success"] and data["aspect"] == "4:3" and data["opacity"] == "sample"
    roles = [role for role, _src, _img in captured["references"]]
    assert roles == ["base_product", "wood_finish", "wood_finish", "wood_finish", "color_patch"]
    assert captured["resolution"] == "2K"
    assert captured["png_meta"]["nano_sofa_product"] == "Meli 160"
    assert captured["png_meta"]["nano_sofa_wood_color_id"] == "dab-miodowy"
    prompt = captured["prompt"]
    assert "Dąb miodowy — warm honey oak (target colour #C49A6C)" in prompt
    # No level chosen + finish photographs → the samples are the coverage authority.
    assert "COVERAGE: match the finish photographs exactly" in prompt
    assert "and how much grain shows through" in prompt
    assert "WOOD FINISH AUTHORITY (images 2, 3, 4)" in prompt
    assert "COLOUR AUTHORITY (image 5)" in prompt
    assert "KEEP EVERYTHING ELSE IDENTICAL" in prompt


def test_recolor_single_reference_model_sends_only_the_photo(client, meli_data, monkeypatch):
    captured = {}

    def fake_generate(**kw):
        captured.update(kw)
        return {"generation_id": "g1", "output_path": kw["references"][0][1], "cost": 0.0,
                "elapsed_ms": 1, "model_id": kw["model"], "resolution": "auto", "quality": ""}

    async def fake_derived(*_a):
        return "/api/outputs/x.jpg", "jpg", False

    monkeypatch.setattr(meli_data, "generate_openrouter", fake_generate)
    monkeypatch.setattr(meli_data, "_derived_url", fake_derived)
    r = client.post("/api/meli/recolor", data={
        "openrouter_key": "sk-or-x", "model": "krea/krea-2-large", "color": "dab-miodowy",
    }, files={"base": ("bed.png", _png(300, 400), "image/png")})
    assert r.json()["references_sent"] == 1
    # No samples can be sent → falls back to the stain default, never "match the samples".
    assert r.json()["opacity"] == 30
    assert "COVERAGE (30% opacity)" in captured["prompt"]
    assert "WOOD FINISH AUTHORITY" not in captured["prompt"]
    assert "COLOUR AUTHORITY" not in captured["prompt"]


def test_recolor_custom_opaque_colour_with_uploaded_sample(client, meli_data, monkeypatch):
    captured = {}

    def fake_generate(**kw):
        captured.update(kw)
        return {"generation_id": "g1", "output_path": kw["references"][0][1], "cost": 0.0,
                "elapsed_ms": 1, "model_id": kw["model"], "resolution": "2K", "quality": ""}

    async def fake_derived(*_a):
        return "/api/outputs/x.jpg", "jpg", False

    monkeypatch.setattr(meli_data, "generate_openrouter", fake_generate)
    monkeypatch.setattr(meli_data, "_derived_url", fake_derived)
    r = client.post("/api/meli/recolor", data={
        "openrouter_key": "sk-or-x", "model": "google/gemini-nano-banana-2.1",
        "custom_name": "grafit satynowy", "custom_hex": "3a3d40", "custom_finish": "opaque",
    }, files=[("base", ("bed.png", _png(), "image/png")),
              ("references", ("s.png", _png(64, 64), "image/png"))])
    assert r.json()["color_id"] == "custom"
    roles = [role for role, _src, _img in captured["references"]]
    assert roles == ["base_product", "wood_finish", "color_patch"]
    assert "COVERAGE (80% opacity)" in captured["prompt"]
    assert "opaque satin paint" in captured["prompt"]
    assert "#3A3D40" in captured["prompt"]


@pytest.mark.parametrize("data,code", [
    ({"model": "google/gemini-nano-banana-2.1", "color": "dab-miodowy"}, "MISSING_OPENROUTER_KEY"),
    ({"openrouter_key": "k", "model": "nope/model", "color": "dab-miodowy"}, "UNKNOWN_MODEL"),
    ({"openrouter_key": "k", "model": "google/gemini-nano-banana-2.1", "color": "nope"}, "UNKNOWN_COLOR"),
    ({"openrouter_key": "k", "model": "google/gemini-nano-banana-2.1"}, "MISSING_COLOR"),
])
def test_recolor_validation(client, meli_data, data, code):
    r = client.post("/api/meli/recolor", data=data, files={"base": ("bed.png", _png(), "image/png")})
    assert r.status_code == 400 and r.json()["error_code"] == code


@pytest.mark.parametrize("sent,expected,phrase", [
    ("10", 10, "clear, transparent oil"),
    ("55", 55, "semi-opaque, pigmented stain"),
    ("62", 55, "semi-opaque, pigmented stain"),
    ("100", 100, "no visible grain pattern"),
])
def test_explicit_opacity_overrides_the_samples(client, meli_data, monkeypatch, sent, expected, phrase):
    captured = {}

    def fake_generate(**kw):
        captured.update(kw)
        return {"generation_id": "g1", "output_path": kw["references"][0][1], "cost": 0.0,
                "elapsed_ms": 1, "model_id": kw["model"], "resolution": "2K", "quality": ""}

    async def fake_derived(*_a):
        return "/api/outputs/x.jpg", "jpg", False

    monkeypatch.setattr(meli_data, "generate_openrouter", fake_generate)
    monkeypatch.setattr(meli_data, "_derived_url", fake_derived)
    r = client.post("/api/meli/recolor", data={
        "openrouter_key": "sk-or-x", "model": "google/gemini-nano-banana-2.1",
        "color": "dab-miodowy", "opacity": sent,
    }, files={"base": ("bed.png", _png(), "image/png")})
    assert r.json()["opacity"] == expected
    prompt = captured["prompt"]
    assert f"COVERAGE ({expected}% opacity)" in prompt and phrase in prompt
    assert "the amount of visible grain follows the COVERAGE level above" in prompt
    assert captured["png_meta"]["nano_sofa_wood_opacity"] == str(expected)
    # Painted wood with no grain: low coverage must invent plausible grain.
    assert ("render a plausible, fine natural grain" in prompt) == (expected <= 55)
