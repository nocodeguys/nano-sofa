"""Colour variants on a locked backdrop are locked to the anchor's scale and
floor line (studio.normalize.match_anchor_geometry) — the prompt's 78-84 %
contract alone let a real set wander 0.90-0.94 in width."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

W, H = 768, 960


def _bed(colour, scale=1.0, dx=0, dy=0, size=(W, H), wall=(244, 242, 238)) -> Image.Image:
    """A synthetic packshot: a warm cyclorama with a soft floor glow, a soft
    contact shadow and a bed (channelled headboard, base, white duvet) whose
    floor point is (384 + dx, 700 + dy), drawn at `scale`."""
    w, h = size
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
    x = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :, None]
    field = np.array(wall, np.float32) + y * 6.0 + 4.0 * np.exp(-((x - 0.3) ** 2 + (y - 0.8) ** 2) / 0.02)
    img = Image.fromarray(np.clip(field + np.zeros((h, w, 3), np.float32), 0, 255).astype(np.uint8))
    fx, fy = 384 + dx, 700 + dy

    def p(px, py):   # bed-local coordinates (floor point at 0, 0) → canvas
        return fx + px * scale, fy + py * scale

    shadow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shadow).ellipse([*p(-330, -12), *p(330, 14)], fill=70)
    shadow = shadow.filter(ImageFilter.GaussianBlur(10 * scale))
    img = Image.composite(Image.new("RGB", (w, h), (200, 196, 190)), img, shadow)

    d = ImageDraw.Draw(img)
    dark = tuple(max(0, c - 28) for c in colour)
    d.rectangle([*p(-300, -330), *p(-40, -150)], fill=colour, outline=dark, width=3)      # headboard
    for i in range(1, 9):
        d.line([*p(-300 + i * 29, -325), *p(-300 + i * 29, -155)], fill=dark, width=3)    # channels
    d.rectangle([*p(-320, -150), *p(320, 0)], fill=colour, outline=dark, width=3)       # base
    d.rectangle([*p(-300, -210), *p(300, -140)], fill=(236, 236, 234), outline=(214, 214, 212), width=3)
    for i in range(1, 6):
        d.line([*p(-280 + i * 90, -205), *p(-250 + i * 90, -145)], fill=(220, 220, 218), width=2)
    return img


def _save(img: Image.Image, path: Path) -> Path:
    img.save(path, format="PNG")
    return path


def _product_box(img: Image.Image, colour) -> tuple[int, int, int, int]:
    """Ground truth for the synthetic bed: pixels close to its upholstery."""
    a = np.asarray(img).astype(np.int32)
    mask = np.abs(a - np.array(colour)).max(axis=2) < 12
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


TAUPE, CREAM = (150, 140, 132), (226, 218, 206)


def test_variant_takes_the_anchors_scale_and_floor_line(server, tmp_path):
    from studio.normalize import match_anchor_geometry
    anchor = _save(_bed(TAUPE), tmp_path / "anchor.png")
    variant = _save(_bed(CREAM, scale=0.92, dx=-18, dy=24), tmp_path / "variant.png")

    _, applied = match_anchor_geometry(variant, anchor)
    assert applied

    want = _product_box(Image.open(anchor).convert("RGB"), TAUPE)
    got = _product_box(Image.open(variant).convert("RGB"), CREAM)
    # Width, floor line and centre within ~1 % of the frame.
    assert abs((got[2] - got[0]) - (want[2] - want[0])) <= W * 0.01
    assert abs(got[3] - want[3]) <= H * 0.01
    assert abs((got[0] + got[2]) / 2 - (want[0] + want[2]) / 2) <= W * 0.01


def test_margins_get_the_backdrop_not_a_seam(server, tmp_path):
    from studio.normalize import match_anchor_geometry
    anchor = _save(_bed(TAUPE), tmp_path / "anchor.png")
    # A larger variant is shrunk onto the anchor (s ≈ 0.91), which uncovers
    # margins of ~35 px left and ~64 px top. A backdrop row and column that
    # cross the margin edge must stay smooth there: no black rim from
    # resampling outside the frame, no step where the fitted field begins.
    variant = _save(_bed(CREAM, scale=1.1), tmp_path / "variant.png")
    _, applied = match_anchor_geometry(variant, anchor)
    assert applied
    a = np.asarray(Image.open(variant).convert("L")).astype(np.float32)
    for line in (a[300, :], a[:, 20]):
        assert np.abs(np.diff(line)).max() <= 3.0
        assert line.min() >= 236


def test_png_metadata_survives_the_lock(server, tmp_path):
    from PIL import PngImagePlugin
    from studio.normalize import match_anchor_geometry
    anchor = _save(_bed(TAUPE), tmp_path / "anchor.png")
    info = PngImagePlugin.PngInfo()
    info.add_text("nano_sofa_color_id", "cream")
    variant = tmp_path / "variant.png"
    _bed(CREAM, scale=0.94).save(variant, format="PNG", pnginfo=info)
    _, applied = match_anchor_geometry(variant, anchor)
    assert applied and Image.open(variant).text["nano_sofa_color_id"] == "cream"


@pytest.mark.parametrize("make_variant", [
    # another pose: a different product layout entirely
    lambda: _other_pose(),
    # another canvas size
    lambda: _bed(CREAM, size=(W, H - 64)),
])
def test_doubtful_pairs_are_left_untouched(server, tmp_path, make_variant):
    from studio.normalize import match_anchor_geometry
    anchor = _save(_bed(TAUPE), tmp_path / "anchor.png")
    variant = _save(make_variant(), tmp_path / "variant.png")
    before = variant.read_bytes()
    _, applied = match_anchor_geometry(variant, anchor)
    assert not applied and variant.read_bytes() == before


def _other_pose() -> Image.Image:
    img = _bed(CREAM).transpose(Image.FLIP_TOP_BOTTOM)
    d = ImageDraw.Draw(img)
    for i in range(12):
        d.ellipse([60 + i * 55, 120 + (i % 3) * 90, 100 + i * 55, 160 + (i % 3) * 90], outline=(90, 80, 70), width=4)
    return img


def test_an_aligned_variant_is_not_resampled(server, tmp_path):
    from studio.normalize import match_anchor_geometry
    anchor = _save(_bed(TAUPE), tmp_path / "anchor.png")
    variant = _save(_bed(CREAM), tmp_path / "variant.png")
    before = variant.read_bytes()
    _, applied = match_anchor_geometry(variant, anchor)
    assert not applied and variant.read_bytes() == before


# --------------------------------------------------------------------------
# Route: /api/generate-set locks variants only on a locked backdrop, hero only
# --------------------------------------------------------------------------
@pytest.fixture()
def set_route(server, monkeypatch, base_image):
    from app.core.generator import GenerationResult
    from studio import routes_generate

    calls = []

    def fake_render(req, openai_key="", quality="", openrouter_key=""):
        out = Path(base_image).parent / f"render-{len(calls)}-{req.upholstery_hex or 'x'}.png"
        Image.new("RGB", (64, 48), (200, 190, 180)).save(out)
        return GenerationResult(
            success=True, generation_id="g", output_path=out, output_image=Image.open(out),
            next_history=[], actual_cost=0.01, attempts=1, error_message=None,
            model_id=req.model_id, resolution="1K",
        )

    def fake_lock(master, anchor):
        calls.append((Path(master), Path(anchor)))
        return master, True

    monkeypatch.setattr(routes_generate, "_render_product", fake_render)
    monkeypatch.setattr(routes_generate, "normalize_packshot", lambda path, profile: (path, False))
    monkeypatch.setattr(routes_generate, "match_anchor_geometry", fake_lock)
    return calls


def _post_set(server, base_image, **fields):
    from fastapi.testclient import TestClient
    data = {"api_key": "AIza-test", "kind": "bed", "mat": "cremona", "size": "160",
            "colors_csv": "taupe,cream,graphite"}
    data.update(fields)
    files = {"base_image": ("base.png", base_image.read_bytes(), "image/png")}
    return TestClient(server.app).post("/api/generate-set", data=data, files=files)


def test_set_on_a_locked_backdrop_locks_every_variant_to_the_anchor(server, base_image, set_route):
    r = _post_set(server, base_image, background="ivory", shot="hero")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(set_route) == 2                                   # two variants, never the anchor
    assert len({anchor for _, anchor in set_route}) == 1
    assert all(master != anchor for master, anchor in set_route)
    assert all(v["geometry_locked"] for v in body["variants"])


@pytest.mark.parametrize("fields", [
    {"background": "ivory", "shot": "close_up"},     # tight shot: no full product
    {"background": "grey", "shot": "hero"},          # studio backdrop without locks
    {"background": "scandi", "shot": "hero"},        # interior
])
def test_set_without_a_locked_hero_is_not_locked(server, base_image, set_route, fields):
    r = _post_set(server, base_image, **fields)
    assert r.status_code == 200, r.text
    assert set_route == []
    assert not any(v.get("geometry_locked") for v in r.json()["variants"])
