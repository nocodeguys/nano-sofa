"""External image engines (OpenRouter Images API, OpenAI Images API): the
request each one sends, and the shared persist / cost / trace tail."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import pytest
from PIL import Image


def _png_b64(color=(120, 100, 80)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class _Resp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _plan(server, base_image, model: str, max_refs: int):
    from app.core.generator import load_freeform_reference_plan
    req = server._build_freeform_request(
        api_key="", text="Sypialnia o świcie", style="magazine_cover", env="japandi",
        tod="golden_hour", lens="", height="", color="velutto-27", mat="cremona",
        people="", model=model, aspect="4:3", res="1K", seed="",
        extra_reference_paths=[base_image], max_refs=max_refs,
    )
    loaded = load_freeform_reference_plan(req, max_refs)
    return req, [(slot.role, slot.source, image) for slot, image in loaded]


@pytest.fixture
def sandbox(server, monkeypatch, tmp_path):
    """Redirect the external engines' output + trace directory to tmp and
    silence the cost DB so tests leave no rows behind."""
    from studio import external_engine
    monkeypatch.setattr(external_engine, "_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(external_engine, "record_generation", lambda rec: None)
    return tmp_path


def test_size_for_aspect_is_exact_and_16_aligned(server):
    from studio.external_engine import ALL_ASPECTS, size_for_aspect
    for aspect in ALL_ASPECTS:
        for res in ("1K", "2K"):
            w, h = (int(v) for v in size_for_aspect(aspect, res).split("x"))
            aw, ah = (int(v) for v in aspect.split(":"))
            assert w % 16 == 0 and h % 16 == 0, (aspect, res)
            assert w * ah == h * aw, (aspect, res)
            assert max(w, h) <= 3840
    assert size_for_aspect("1:1") == "1024x1024"
    assert size_for_aspect("3:2") == "1536x1024"
    assert size_for_aspect("2:3") == "1024x1536"
    assert size_for_aspect("4:3", "2K") == "2304x1728"
    assert size_for_aspect("unknown") == "1024x1024"


def test_openrouter_sends_full_plan_quality_and_writes_trace(server, base_image, sandbox, monkeypatch):
    from studio import openrouter
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["headers"] = kwargs["headers"]
        return _Resp(200, {"data": [{"b64_json": _png_b64()}], "usage": {"cost": 0.031}})

    monkeypatch.setattr(openrouter.httpx, "post", fake_post)
    req, plan = _plan(server, base_image, "openai/gpt-image-2", 16)
    assert [role for role, _s, _i in plan] == [
        "material_macro", "color_patch", "material_left", "material_right",
        "material_behavior", "material_application", "extra_reference_1",
    ]

    out = openrouter.generate_openrouter(
        api_key="sk-or-test", model="openai/gpt-image-2", prompt=req.freeform_prompt,
        aspect="4:3", references=plan, quality="medium",
        png_meta={"nano_sofa_material": req.upholstery_material},
        prompt_summary="Sypialnia", trace_request=req,
    )

    body = captured["json"]
    assert captured["url"].endswith("/api/v1/images")
    assert body["model"] == "openai/gpt-image-2"
    assert body["aspect_ratio"] == "4:3"
    assert body["quality"] == "medium"
    assert len(body["input_references"]) == 7
    assert all(r["image_url"]["url"].startswith("data:image/") for r in body["input_references"])
    assert body["prompt"] == req.freeform_prompt
    assert "sk-or-test" in captured["headers"]["Authorization"]

    assert out["cost"] == pytest.approx(0.031)
    assert out["quality"] == "medium" and out["resolution"] == "auto"
    assert Path(out["output_path"]).is_file()
    trace = json.loads((sandbox / "traces" / f"{out['generation_id']}.json").read_text())
    assert trace["model_id"] == "openai/gpt-image-2"
    assert trace["engine"] == "openrouter"
    assert trace["quality"] == "medium"
    assert [r["role"] for r in trace["references"]] == [role for role, _s, _i in plan]
    assert trace["references"][1]["source"].startswith("color-patch:#122D24")
    assert trace["result"]["actual_cost"] == pytest.approx(0.031)
    assert trace["variant"]["material_id"] == "cremona"


def test_openrouter_models_without_quality_do_not_send_it(server, base_image, sandbox, monkeypatch):
    from studio import openrouter
    captured = {}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs["json"]
        return _Resp(200, {"data": [{"b64_json": _png_b64()}], "usage": {"cost": 0.06}})

    monkeypatch.setattr(openrouter.httpx, "post", fake_post)
    req, plan = _plan(server, base_image, "black-forest-labs/flux.2-pro", 8)
    openrouter.generate_openrouter(
        api_key="k", model="black-forest-labs/flux.2-pro", prompt=req.freeform_prompt,
        aspect="4:3", references=plan, quality="high",
    )
    assert "quality" not in captured["json"]
    assert len(captured["json"]["input_references"]) == 7


def test_openai_edit_call_is_multipart_with_fidelity_and_size(server, base_image, sandbox, monkeypatch):
    from studio import openai_images
    captured = {}
    usage = {
        "input_tokens": 1200,
        "input_tokens_details": {"text_tokens": 400, "image_tokens": 800},
        "output_tokens": 4160,
    }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs.get("data")
        captured["files"] = kwargs.get("files")
        captured["json"] = kwargs.get("json")
        captured["headers"] = kwargs["headers"]
        return _Resp(200, {"data": [{"b64_json": _png_b64()}], "usage": usage})

    monkeypatch.setattr(openai_images.httpx, "post", fake_post)
    req, plan = _plan(server, base_image, "gpt-image-2.5-flare", 16)
    out = openai_images.generate_openai(
        api_key="sk-test", model="gpt-image-2.5-flare", prompt=req.freeform_prompt,
        aspect="4:3", resolution="1K", references=plan, quality="xhigh",
        trace_request=req,
    )

    assert captured["url"].endswith("/v1/images/edits")
    assert captured["json"] is None
    data = captured["data"]
    assert data["model"] == "gpt-image-2.5-flare"
    assert data["size"] == "1536x1152"
    assert data["quality"] == "xhigh"
    # GPT Image 2.5 refuses input_fidelity (verified live) — never send it there.
    assert "input_fidelity" not in data
    assert data["output_format"] == "png"
    files = captured["files"]
    assert len(files) == 7 and all(field == "image[]" for field, _spec in files)
    # The colour patch is synthetic → PNG; curated JPEGs travel as JPEG.
    assert files[1][1][2] == "image/png"
    assert files[0][1][2] == "image/jpeg"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"

    expected_cost = 400 * 5e-6 + 800 * 8e-6 + 4160 * 30e-6
    assert out["cost"] == pytest.approx(expected_cost)
    assert out["resolution"] == "1K" and out["quality"] == "xhigh" and out["size"] == "1536x1152"
    trace = json.loads((sandbox / "traces" / f"{out['generation_id']}.json").read_text())
    assert trace["engine"] == "openai" and trace["model_id"] == "gpt-image-2.5-flare"
    assert trace["size"] == "1536x1152" and trace["usage"] == usage
    assert len(trace["references"]) == 7


def test_openai_generation_without_references_is_json(server, sandbox, monkeypatch):
    from studio import openai_images
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["data"] = kwargs.get("data")
        return _Resp(200, {"data": [{"b64_json": _png_b64()}], "usage": {"output_tokens": 1056}})

    monkeypatch.setattr(openai_images.httpx, "post", fake_post)
    out = openai_images.generate_openai(
        api_key="sk-test", model="gpt-image-2.5-sunburst", prompt="A calm bedroom",
        aspect="16:9", resolution="2K", references=[], quality="not-a-tier",
    )
    assert captured["url"].endswith("/v1/images/generations")
    assert captured["data"] is None
    body = captured["json"]
    assert body["size"] == "2304x1296"
    assert body["quality"] == "high"          # unknown tier → model default
    assert "input_fidelity" not in body
    assert out["cost"] == pytest.approx(1056 * 30e-6)
    assert out["resolution"] == "2K"


def test_openai_errors_are_classified(server, sandbox, monkeypatch):
    from studio import openai_images
    from studio.external_engine import ExternalEngineError

    def make(status, payload):
        def fake_post(url, **kwargs):
            return _Resp(status, payload)
        return fake_post

    cases = [
        (401, {"error": {"message": "bad key", "code": "invalid_api_key"}}, "INVALID_OPENAI_KEY", 401),
        (429, {"error": {"message": "quota", "code": "insufficient_quota"}}, "OPENAI_NO_CREDITS", 402),
        (429, {"error": {"message": "slow down", "code": "rate_limit_exceeded"}}, "RATE_LIMITED", 429),
        (400, {"error": {"message": "blocked", "code": "moderation_blocked"}}, "OPENAI_BLOCKED", 400),
        (400, {"error": {"message": "bad size", "code": "invalid_value"}}, "OPENAI_BAD_REQUEST", 400),
        (503, {"error": {"message": "down"}}, "OPENAI_ERROR", 502),
    ]
    for status, payload, code, http_status in cases:
        monkeypatch.setattr(openai_images.httpx, "post", make(status, payload))
        with pytest.raises(ExternalEngineError) as excinfo:
            openai_images.generate_openai(api_key="k", model="gpt-image-2.5-flare",
                                          prompt="x", aspect="1:1")
        assert excinfo.value.code == code, (status, payload)
        assert excinfo.value.http_status == http_status
        assert payload["error"]["message"] in excinfo.value.detail


# --------------------------------------------------------------------------- #
# Lab tab: the product pipeline (base photo + full reference plan + variant
# prompt) on the OpenAI Images API.
# --------------------------------------------------------------------------- #

def _bed_request(server, base_image, **overrides):
    values = dict(
        api_key="", kind="bed", color="velutto-27", color_custom="",
        mat="cremona", mat_notes="", size="160", legs="keep", cam="studio",
        lens="50mm_natural", tod="noon_neutral", shadow="soft_diffuse",
        env="", env_note="", env_mode="", model="gpt-image-2.5-sunburst",
        aspect="4:3", res="2K", seed="", base_image_path=base_image,
        scene_image_path=None,
    )
    values.update(overrides)
    return server._build_generation_request(**values)


def test_product_pipeline_on_openai_sends_base_and_reference_plan(server, base_image, sandbox, monkeypatch):
    from dataclasses import replace
    from studio import openai_images
    captured = {}
    usage = {"input_tokens_details": {"text_tokens": 900, "image_tokens": 5000}, "output_tokens": 6000}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs.get("data")
        captured["files"] = kwargs.get("files")
        return _Resp(200, {"data": [{"b64_json": _png_b64()}], "usage": usage})

    monkeypatch.setattr(openai_images.httpx, "post", fake_post)
    req = replace(_bed_request(server, base_image), engine_quality="max")
    result = openai_images.generate_product_openai(req, "sk-test")

    assert result.success, result.error_message
    assert result.model_id == "gpt-image-2.5-sunburst" and result.resolution == "2K"
    assert captured["url"].endswith("/v1/images/edits")
    data = captured["data"]
    assert data["quality"] == "max" and "input_fidelity" not in data
    assert data["size"] == "2304x1728"
    # slot 1 is the base photo, then the material set + colour patch, in the
    # product pipeline's own order — and the prompt is the variant prompt.
    trace = json.loads((sandbox / "traces" / f"{result.generation_id}.json").read_text())
    roles = [r["role"] for r in trace["references"]]
    assert roles[0] == "base_product"
    assert {"material_macro", "color_patch", "material_left", "material_right",
            "material_behavior", "material_application"} <= set(roles)
    assert len(captured["files"]) == len(roles)
    assert "slot 1" in data["prompt"] and "COLOUR AUTHORITY" in data["prompt"]
    assert "BRIEF:" not in data["prompt"]
    assert trace["engine"] == "openai" and trace["variant"]["product_type"] == "bed"
    assert result.actual_cost == pytest.approx(900 * 5e-6 + 5000 * 8e-6 + 6000 * 30e-6)
    assert Path(result.output_path).is_file() and result.output_image is not None


def test_product_pipeline_on_openai_reports_engine_errors_as_results(server, base_image, sandbox, monkeypatch):
    from studio import openai_images

    def fake_post(url, **kwargs):
        return _Resp(429, {"error": {"message": "quota", "code": "insufficient_quota"}})

    monkeypatch.setattr(openai_images.httpx, "post", fake_post)
    result = openai_images.generate_product_openai(_bed_request(server, base_image), "sk-test")
    assert not result.success
    assert result.error_code == "OPENAI_NO_CREDITS" and result.http_status == 402
    assert result.output_path is None


def test_product_routes_require_openai_key_for_lab_models(server, base_image):
    from fastapi.testclient import TestClient
    client = TestClient(server.app)
    with open(base_image, "rb") as fh:
        r = client.post("/api/generate", data={"api_key": "AIza-x", "kind": "bed",
                                               "model": "gpt-image-2.5-flare"},
                        files={"base_image": ("base.png", fh, "image/png")})
    assert r.json()["error_code"] == "MISSING_OPENAI_KEY"
    r = client.post("/api/generate-set", data={"api_key": "AIza-x", "model": "gpt-image-2.5-sunburst"})
    assert r.json()["error_code"] == "MISSING_OPENAI_KEY"
    # A Gemini model still needs the Gemini key, an OpenAI key alone won't do.
    r = client.post("/api/generate", data={"openai_key": "sk-x", "model": "gemini-3.1-flash-image"})
    assert r.json()["error_code"] == "MISSING_API_KEY"


def test_openai_falls_back_to_standard_size_when_custom_size_is_refused(server, sandbox, monkeypatch):
    from studio import openai_images
    sizes = []

    def fake_post(url, **kwargs):
        body = kwargs.get("json") or kwargs.get("data")
        sizes.append(body["size"])
        if len(sizes) == 1:
            return _Resp(400, {"error": {"message": "Invalid value: '1536x1152'. Supported values are: '1024x1024', '1536x1024', '1024x1536', 'auto'.", "param": "size", "code": "invalid_value"}})
        return _Resp(200, {"data": [{"b64_json": _png_b64()}], "usage": {"output_tokens": 10}})

    monkeypatch.setattr(openai_images.httpx, "post", fake_post)
    out = openai_images.generate_openai(api_key="k", model="gpt-image-2.5-flare", prompt="x", aspect="4:3")
    assert sizes == ["1536x1152", "1536x1024"]
    assert out["size"] == "1536x1024"


def test_openai_retries_without_input_fidelity_when_model_refuses_it(server, sandbox, monkeypatch, base_image):
    from studio import openai_images
    monkeypatch.setitem(openai_images.OPENAI_MODELS, "gpt-image-test-fidelity",
                        {**openai_images.OPENAI_MODELS["gpt-image-2.5-flare"], "input_fidelity": True})
    seen = []

    def fake_post(url, **kwargs):
        data = kwargs.get("data")
        seen.append("input_fidelity" in data)
        if "input_fidelity" in data:
            return _Resp(400, {"error": {"message": "The model does not support the 'input_fidelity' parameter.",
                                         "param": "input_fidelity", "code": "invalid_input_fidelity_model"}})
        return _Resp(200, {"data": [{"b64_json": _png_b64()}], "usage": {"output_tokens": 10}})

    monkeypatch.setattr(openai_images.httpx, "post", fake_post)
    img = Image.open(base_image)
    out = openai_images.generate_openai(api_key="k", model="gpt-image-test-fidelity", prompt="x",
                                        aspect="4:3", references=[("base_product", base_image, img)])
    assert seen == [True, False]
    assert Path(out["output_path"]).is_file()


def test_product_pipeline_on_openrouter_matches_the_openai_request(server, base_image, sandbox, monkeypatch):
    """Lab wizard via OpenRouter: same base photo + reference plan + variant
    prompt as the OpenAI-direct path, sent as input_references."""
    from dataclasses import replace
    from studio import openrouter
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return _Resp(200, {"data": [{"b64_json": _png_b64()}], "usage": {"cost": 0.05}})

    monkeypatch.setattr(openrouter.httpx, "post", fake_post)
    req = replace(_bed_request(server, base_image, model="openai/gpt-image-2.5-sunburst"),
                  engine_quality="xhigh")
    result = openrouter.generate_product_openrouter(req, "sk-or-test")

    assert result.success, result.error_message
    body = captured["json"]
    assert captured["url"].endswith("/api/v1/images")
    assert body["model"] == "openai/gpt-image-2.5-sunburst"
    assert body["quality"] == "xhigh" and body["aspect_ratio"] == "4:3"
    trace = json.loads((sandbox / "traces" / f"{result.generation_id}.json").read_text())
    roles = [r["role"] for r in trace["references"]]
    assert roles[0] == "base_product"
    assert {"material_macro", "color_patch", "material_left", "material_right",
            "material_behavior", "material_application"} <= set(roles)
    assert len(body["input_references"]) == len(roles)
    assert "slot 1" in body["prompt"] and "COLOUR AUTHORITY" in body["prompt"]
    assert "BRIEF:" not in body["prompt"]
    assert trace["engine"] == "openrouter"
    assert result.actual_cost == pytest.approx(0.05)


def test_product_routes_require_openrouter_key_for_openrouter_lab_models(server, base_image):
    from fastapi.testclient import TestClient
    client = TestClient(server.app)
    with open(base_image, "rb") as fh:
        r = client.post("/api/generate", data={"api_key": "AIza-x", "openai_key": "sk-x",
                                               "kind": "bed", "model": "openai/gpt-image-2.5-flare"},
                        files={"base_image": ("base.png", fh, "image/png")})
    assert r.json()["error_code"] == "MISSING_OPENROUTER_KEY"


def test_lab_config_lists_openrouter_product_models(server):
    from fastapi.testclient import TestClient
    cfg = TestClient(server.app).get("/api/config").json()
    lab = {m["id"]: m for m in cfg["lab_models"]}
    assert lab["gpt-image-2.5-flare"]["provider"] == "openai"
    assert lab["openai/gpt-image-2.5-flare"]["provider"] == "openrouter"
    assert lab["openai/gpt-image-2.5-sunburst"]["qualities"][-1] == "max"
    # FLUX / Seedream stay editorial-only — they don't preserve product geometry.
    assert not any("flux" in mid or "seedream" in mid for mid in lab)
