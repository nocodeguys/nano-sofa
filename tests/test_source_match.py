"""Seria recolors follow the source photo's geometry, not the page pickers."""
from __future__ import annotations

from PIL import Image, PngImagePlugin


def _png(path, size, text=None):
    info = PngImagePlugin.PngInfo()
    for k, v in (text or {}).items():
        info.add_text(k, v)
    Image.new("RGB", size, (120, 110, 100)).save(path, format="PNG", pnginfo=info)
    return path


def test_match_follows_source_aspect_and_tier(server, tmp_path):
    from studio.source_match import match_source_output

    # A 1K 4:3 render recoloured while the pickers say 4:5 / 2K.
    src = _png(tmp_path / "a.png", (1200, 896))
    assert match_source_output("gemini-3.1-flash-image", src, "4:5", "2K") == ("4:3", "1K", (1200, 896))

    # A 2K portrait render stays 2K portrait.
    src = _png(tmp_path / "b.png", (1856, 2304))
    assert match_source_output("gemini-3.1-flash-image", src, "4:3", "1K")[:2] == ("4:5", "2K")

    # A 1K-capped model never asks for more than it has.
    src = _png(tmp_path / "c.png", (4000, 3000))
    assert match_source_output("gemini-2.5-flash-image", src, "4:3", "1K")[1] == "1K"


def test_match_falls_back_when_source_unreadable(server, tmp_path):
    from studio.source_match import match_source_output

    assert match_source_output("gemini-3.1-flash-image", tmp_path / "missing.png", "4:3", "2K") == ("4:3", "2K", None)


def test_fit_to_source_crops_resizes_and_keeps_identity(server, tmp_path):
    from studio.source_match import fit_to_source

    out = _png(tmp_path / "out.png", (2400, 1792), {"nano_sofa_generation_id": "abc"})
    fit_to_source(out, (1200, 900))
    with Image.open(out) as im:
        assert im.size == (1200, 900)
        assert im.text["nano_sofa_generation_id"] == "abc"


def test_fit_to_source_does_not_upscale_a_capped_render(server, tmp_path):
    from studio.source_match import fit_to_source

    out = _png(tmp_path / "out.png", (1200, 896))
    fit_to_source(out, (4000, 3000))
    with Image.open(out) as im:
        assert im.size[0] <= 1200
        assert abs(im.size[0] / im.size[1] - 4000 / 3000) < 0.01
