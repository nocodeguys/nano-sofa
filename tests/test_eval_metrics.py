"""The eval metrics must measure what they claim on images we fully control."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import eval_report as er  # noqa: E402


@pytest.mark.parametrize("lab1,lab2,expected", [
    # Sharma et al. 2005 reference pairs
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2592, 0.3350), 1.0000),
])
def test_delta_e2000_reference_pairs(lab1, lab2, expected):
    assert float(er.delta_e2000(np.array(lab1), np.array(lab2))) == pytest.approx(expected, abs=1e-3)


def test_srgb_to_lab_white_and_grey():
    white = er.srgb_to_lab(np.array([255, 255, 255]))
    assert white[0] == pytest.approx(100.0, abs=0.01)
    assert abs(white[1]) < 0.01 and abs(white[2]) < 0.01
    mid = er.srgb_to_lab(np.array([119, 119, 119]))
    assert mid[0] == pytest.approx(50.0, abs=0.5)


def _synthetic(tmp_path: Path, *, bg="#F7F5F1", fabric="#938A83", width_share=0.80,
               with_bedding=True) -> Path:
    w, h = 800, 600
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    pw = int(w * width_share)
    x0 = (w - pw) // 2
    y0, y1 = int(h * 0.30), int(h * 0.85)
    d.rectangle([x0, y0, x0 + pw - 1, y1], fill=fabric)          # upholstered frame
    if with_bedding:
        # off-white linen, far enough from the backdrop to count as product
        d.rectangle([x0 + 40, y0 + 30, x0 + pw - 41, y1 - 60], fill="#D9D4CD")
    path = tmp_path / "synthetic.png"
    img.save(path)
    return path


def test_measure_recovers_colour_and_framing(tmp_path):
    path = _synthetic(tmp_path)
    m = er.measure(path, "#938A83", "#F7F5F1")
    assert m["backdrop_known"] is True
    assert m["backdrop_de"] < 0.5
    assert m["product_width_share"] == pytest.approx(0.80, abs=0.02)
    assert m["upholstery_de"] < 1.0, m
    assert m["upholstery_hex"].upper() == "#938A83"
    # bedding takes most of the rectangle, so the fabric cluster is a minority
    assert 0.05 < m["upholstery_share"] < 0.6


def test_measure_flags_wrong_colour(tmp_path):
    path = _synthetic(tmp_path, fabric="#6A7763")   # olive instead of taupe
    m = er.measure(path, "#938A83", "#F7F5F1")
    assert m["upholstery_de"] > 10


def test_measure_macro_fills_frame(tmp_path):
    path = _synthetic(tmp_path, width_share=1.0, with_bedding=False)
    img = Image.open(path)
    # make it a full-frame fabric crop
    full = Image.new("RGB", img.size, "#938A83")
    full.save(path)
    m = er.measure(path, "#938A83", "#F7F5F1")
    # the border IS the fabric now, so the mask collapses — that is the
    # signal: mask_share near 0 with backdrop_de huge means "no backdrop seen"
    assert m["backdrop_de"] > 10
