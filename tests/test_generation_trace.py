import json

from PIL import Image

from app.core.generation_trace import build_generation_trace, write_generation_trace
from app.core.generator import GenerationRequest


def _request(model="gemini-3.1-flash-image"):
    return GenerationRequest(
        model_id=model,
        base_product_image=Image.new("RGB", (8, 6), "white"),
        scene_reference_image=Image.new("RGB", (4, 3), "ivory"),
        swatch_reference_image=Image.new("RGB", (5, 5), "beige"),
        api_key="must-never-be-serialized",
        aspect_ratio="4:5",
        resolution="2K",
    )


def _trace(req):
    refs = [
        req.base_product_image,
        req.scene_reference_image,
        req.swatch_reference_image,
    ]
    return build_generation_trace(
        req=req,
        generation_id="generation-1",
        prompt="effective prompt",
        effective_system_instruction="system prompt",
        reference_images=refs,
    )


def test_trace_has_stable_order_hashes_and_no_api_key():
    trace = _trace(_request())

    assert [ref["role"] for ref in trace["references"]] == [
        "base_product", "scene", "material_macro"
    ]
    assert all(len(ref["sha256_rgb"]) == 64 for ref in trace["references"])
    assert "must-never-be-serialized" not in json.dumps(trace)
    assert trace["prompt"] == "effective prompt"
    assert trace["variant"]["product_type"] == "sofa"
    assert trace["variant"]["material"] == "bouclé"


def test_setup_fingerprint_groups_cross_model_ab_but_exact_does_not():
    flash = _trace(_request("gemini-3.1-flash-image"))
    pro = _trace(_request("gemini-3-pro-image"))

    assert flash["setup_fingerprint"] == pro["setup_fingerprint"]
    assert flash["exact_fingerprint"] != pro["exact_fingerprint"]


def test_trace_writer_creates_readable_manifest(tmp_path):
    trace = _trace(_request())
    path = write_generation_trace(trace, tmp_path / "traces")

    assert json.loads(path.read_text(encoding="utf-8"))["generation_id"] == "generation-1"
