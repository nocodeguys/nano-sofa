"""Catalog-consistency guards: the locked profile, the numeric framing
contract, and the deterministic packshot normalization.

Together these are what make a product grid read as one photo session instead
of N separate ones. Each layer has a distinct failure mode worth pinning:
  * the locks silently not applying → two products shot on different backdrops,
  * the contract missing → subject scale left to the model's interpretation,
  * normalization applying to the wrong kind of render → a lifestyle shot or a
    macro crop mangled into a packshot.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_V2 = REPO_ROOT / "app-v2"
if str(APP_V2) not in sys.path:
    sys.path.insert(0, str(APP_V2))

from app.core.generator import _build_prompt_text  # noqa: E402
from studio.normalize import (  # noqa: E402
    CATALOG_PROFILE,
    PROFILES,
    _backdrop,
    _recover_pale_textile_detail,
    is_raw_copy,
    normalize_packshot,
    resolve_profile,
)


def _request(server, base_image, **over):
    kwargs = dict(
        api_key="test-key",
        kind="bed",
        color="greige", color_custom="",
        mat="boucle", mat_notes="",
        size="160",
        legs="keep",
        cam="studio",
        lens="35mm_wide", tod="golden_hour", shadow="hard_studio_5",
        env="cyclorama_warm", env_note="", env_mode="",
        model="gemini-2.5-flash-image", aspect="4:3", res="1K", seed="",
        base_image_path=base_image,
        scene_image_path=None,
    )
    kwargs.update(over)
    return server._build_generation_request(**kwargs)


# --------------------------------------------------------------------------
# The locked profile
# --------------------------------------------------------------------------
def test_catalog_mode_overrides_look_settings(server, base_image):
    """Catalog mode ignores conflicting look settings — that is its whole job."""
    req = _request(server, base_image, catalog=True)

    assert req.focal_length_mm == 85          # 85mm_product, not the 35mm asked for
    assert req.aperture == "f/8.0"            # deep, not the default standard
    assert "golden" not in req.tod_description.lower()
    assert "hard" not in req.shadow_description.lower()


@pytest.mark.parametrize("profile,hex_tone", [
    ("ivory", "#F7F5F1"),
    ("atelier", "#A8A292"),
    ("softblush", "#FAF8F6"),
    ("neutral", "#FAFAFA"),
    ("paperwhite", "#FCFAF7"),
])
def test_each_backdrop_profile_selects_its_cyclorama(server, base_image, profile, hex_tone):
    """The written backdrop spec and the normalization profile must name the
    same tone, or the post-pass repaints the render instead of nudging it."""
    req = _request(server, base_image, catalog=True, catalog_profile=profile)
    assert hex_tone in req.env_description
    assert resolve_profile(profile).name == profile


def test_default_backdrop_is_warm_not_clinical(server, base_image):
    """A pure-white cyclorama reads as clinical for an interiors brand."""
    req = _request(server, base_image, catalog=True)
    assert "#F7F5F1" in req.env_description
    assert CATALOG_PROFILE.name == "ivory"


def test_unknown_profile_falls_back_instead_of_failing(server, base_image):
    req = _request(server, base_image, catalog=True, catalog_profile="nie-ma-takiego")
    assert "#F7F5F1" in req.env_description


@pytest.mark.parametrize("profile,filename", [
    ("ivory", "cyclorama_architectural.png"),
    ("atelier", "cyclorama_atelier_gradient.png"),
    ("softblush", "cyclorama_softblush.png"),
])
def test_catalog_uses_its_canonical_empty_studio_reference(
    server, base_image, profile, filename
):
    req = _request(
        server, base_image, catalog=True, catalog_profile=profile,
        env="loft", env_note="yellow sunset", env_mode="background",
        scene_image_path=base_image, preserve_camera_from_base=True,
    )
    assert Path(req.scene_reference_image).name == filename
    assert "yellow sunset" not in req.notes
    assert not req.preserve_camera_from_base


def test_catalog_mode_keeps_yaw(server, base_image):
    """Which way a product faces stays a per-product decision."""
    req = _request(server, base_image, catalog=True, yaw="side_right")
    assert req.camera_angle == "side-right"


def test_without_catalog_mode_nothing_is_forced(server, base_image):
    req = _request(server, base_image, catalog=False)
    assert req.focal_length_mm == 35
    assert req.catalog_framing_contract == ""


# --------------------------------------------------------------------------
# The numeric framing contract
# --------------------------------------------------------------------------
def test_framing_contract_reaches_the_prompt(server, base_image):
    req = _request(server, base_image, catalog=True)
    assert "CATALOG FRAMING CONTRACT" in req.catalog_framing_contract
    assert "78-84 percent" in req.catalog_framing_contract
    assert "CATALOG FRAMING CONTRACT" in _build_prompt_text(req)


def test_framing_contract_survives_reference_lock(server, base_image, tmp_path):
    """The anchor was rendered under the same contract, so the two agree — the
    contract must not be swallowed by the reference-lock short-circuit."""
    ref = tmp_path / "anchor.png"
    Image.new("RGB", (16, 16), (250, 250, 250)).save(ref)
    req = _request(
        server, base_image, catalog=True,
        extra_reference_paths=[ref], lock_to_reference=True,
    )
    text = _build_prompt_text(req)
    assert "REFERENCE LOCK" in text
    assert "CATALOG FRAMING CONTRACT" in text


@pytest.mark.parametrize("shot", ["detail_fabric", "detail_corner", "close_up"])
def test_no_framing_contract_for_crops(server, base_image, shot):
    """A macro crop has no subject-scale-within-the-frame to lock."""
    req = _request(server, base_image, catalog=True, shot=shot)
    assert req.catalog_framing_contract == ""
    assert req.shot_type == shot          # and the crop is not forced back to hero


# --------------------------------------------------------------------------
# Deterministic normalization
# --------------------------------------------------------------------------
def _packshot(path: Path, *, bg, box, size=(600, 450)):
    """A synthetic packshot: one dark rectangle on a flat backdrop."""
    img = Image.new("RGB", size, bg)
    ImageDraw.Draw(img).rectangle(box, fill=(90, 80, 70))
    img.save(path)
    return path


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_normalization_lands_on_the_profile_backdrop(tmp_path, name):
    """Every profile must land close to its calibrated studio anchors.

    Pale-product profiles use a whole-frame photographic calibration rather
    than a destructive cut-out, so highlight roll-off may move an anchor by a
    few values while remaining deterministic.
    """
    prof = PROFILES[name]
    p = _packshot(tmp_path / f"{name}.png", bg=(238, 235, 228), box=(120, 150, 400, 300))
    _, applied = normalize_packshot(p, name)
    assert applied

    arr = np.asarray(Image.open(p).convert("RGB")).astype(int)
    h = arr.shape[0]
    if prof.top_left_rgb is not None:
        # Directional profiles vary on both axes and may include a fixed
        # sub-RGB grain, so compare the four anchors with a tiny tolerance.
        assert np.allclose(arr[0, 6], prof.top_left_rgb, atol=12)
        assert np.allclose(arr[0, -7], prof.top_right_rgb, atol=12)
        assert np.allclose(arr[-1, 6], prof.floor_left_rgb, atol=12)
        assert np.allclose(arr[-1, -7], prof.floor_right_rgb, atol=12)
    else:
        assert np.allclose(arr[0, 6], prof.top_rgb, atol=6)
        assert np.allclose(arr[int(h * prof.baseline_frac), 6], prof.background, atol=6)
        assert np.allclose(arr[-1, 6], prof.floor_rgb, atol=6)


def test_atelier_backdrop_has_lateral_depth_and_fixed_pixels():
    """The supplied table reference is a two-axis lit cyclorama, not a flat
    beige field. It must be darker/olive left and pale blush right, and repeated
    builds at one size must be byte-identical despite the photographic grain."""
    prof = PROFILES["atelier"]
    a = _backdrop((600, 450), prof)
    b = _backdrop((600, 450), prof)
    assert a.tobytes() == b.tobytes()

    arr = np.asarray(a).astype(int)
    assert arr[30, 30].mean() + 35 < arr[-30, -30].mean()
    assert arr[30, 30, 1] > arr[30, 30, 2]  # olive/stone, not neutral grey
    assert abs(arr[-30, -30, 0] - arr[-30, -30, 2]) < 10  # dusty blush


def test_softblush_backdrop_keeps_one_catalog_colour():
    """The bed-grid reference is #FAF8F6 outside the product/shadow; it should
    not acquire the directional wash used by the atelier profile."""
    arr = np.asarray(_backdrop((600, 450), PROFILES["softblush"]))
    assert np.unique(arr.reshape(-1, 3), axis=0).tolist() == [[250, 248, 246]]


def test_normalization_handles_a_two_axis_source_cyclorama(tmp_path):
    """Regression for the rectangular stale-backdrop artifact: a lateral wash
    must be estimated as background rather than included in the product crop."""
    p = tmp_path / "directional.png"
    source = _backdrop((600, 450), PROFILES["atelier"])
    ImageDraw.Draw(source).rounded_rectangle(
        (135, 145, 465, 320), radius=24, fill=(82, 72, 62)
    )
    source.save(p)

    _, applied = normalize_packshot(p, "atelier")
    assert applied
    arr = np.asarray(Image.open(p).convert("RGB"))
    # The top band is pure rebuilt studio; no block of the source light field
    # survives around the normalized product.
    expected = np.asarray(_backdrop((600, 450), PROFILES["atelier"]))
    assert np.allclose(arr[:70], expected[:70], atol=5)


def test_backdrop_is_lit_not_flat_filled(tmp_path):
    """A flat fill is the tell that a packshot was composited. The backdrop
    must carry a wash — and it must be smooth, with no banding."""
    p = _packshot(tmp_path / "grad.png", bg=(238, 235, 228), box=(120, 150, 400, 300))
    normalize_packshot(p, "ivory")

    col = np.asarray(Image.open(p).convert("RGB")).astype(int)[:, 4, :]
    assert not np.array_equal(col[0], col[-1]), "backdrop is flat"
    assert np.abs(np.diff(col, axis=0)).max() <= 1, "visible banding in the backdrop"


def test_pale_profiles_lock_the_bottom_catalog_band(tmp_path):
    """The last five percent is guaranteed empty floor and must be identical
    across products, even when Gemini supplies two different source washes."""
    a = _packshot(tmp_path / "warm.png", bg=(246, 239, 224), box=(105, 150, 390, 330))
    b = _packshot(tmp_path / "cool.png", bg=(229, 235, 241), box=(190, 125, 510, 320))
    normalize_packshot(a, "ivory")
    normalize_packshot(b, "ivory")

    arr_a = np.asarray(Image.open(a).convert("RGB"))
    arr_b = np.asarray(Image.open(b).convert("RGB"))
    y = round(arr_a.shape[0] * 0.95)
    assert np.array_equal(arr_a[y:], arr_b[y:])


def test_white_textile_detail_recovery_leaves_smooth_backdrop_untouched():
    """Local contrast belongs on textured bedding, never on the studio plate."""
    arr = np.full((180, 240, 3), (247, 245, 241), dtype=np.uint8)
    # Bright neutral duvet with shallow folds and a fine weave-like modulation.
    yy, xx = np.mgrid[0:70, 0:140]
    folds = 247 + np.rint(3.0 * np.sin(xx / 8.0) + 1.2 * np.sin(yy / 3.0))
    arr[70:140, 50:190] = np.clip(folds[..., None], 0, 255).astype(np.uint8)
    before = arr.copy()

    out = np.asarray(_recover_pale_textile_detail(Image.fromarray(arr, "RGB")))
    assert np.array_equal(out[:55], before[:55]), "smooth canonical backdrop changed"
    assert out[82:128, 65:175].std() > before[82:128, 65:175].std()
    assert out[82:128, 65:175].max() <= before[82:128, 65:175].max()


def test_normalization_gives_different_products_the_same_geometry(tmp_path):
    """Two products at wildly different scales must come out matched — this is
    the exact defect a catalog grid shows as 'every tile is a different size'."""
    a = _packshot(tmp_path / "small.png", bg=(240, 240, 240), box=(240, 250, 360, 310))
    b = _packshot(tmp_path / "big.png", bg=(228, 226, 220), box=(60, 90, 540, 380))
    for p in (a, b):
        _, applied = normalize_packshot(p, "neutral")
        assert applied

    def geometry(path):
        arr = np.asarray(Image.open(path).convert("RGB")).astype(int)
        mask = np.abs(arr - np.array(PROFILES["neutral"].background)).max(axis=2) > 40
        ys, xs = np.nonzero(mask)
        h, w = mask.shape
        return (xs.max() - xs.min()) / w, ys.max() / h

    wa, ba = geometry(a)
    wb, bb = geometry(b)
    assert wa == pytest.approx(wb, abs=0.03), "subject scale must match"
    assert ba == pytest.approx(bb, abs=0.02), "floor line must match"
    assert ba == pytest.approx(CATALOG_PROFILE.baseline_frac, abs=0.03)


def test_normalization_keeps_the_untouched_render(tmp_path):
    p = _packshot(tmp_path / "c.png", bg=(236, 233, 226), box=(150, 160, 430, 320))
    before = Image.open(p).convert("RGB").tobytes()
    normalize_packshot(p)

    raw = p.with_suffix(".raw.png")
    assert raw.exists() and is_raw_copy(raw)
    assert Image.open(raw).convert("RGB").tobytes() == before


def test_normalization_refuses_a_bleeding_crop(tmp_path):
    """A product running off the frame edge is a crop or a lifestyle shot;
    rescaling it onto a packshot baseline would be wrong."""
    p = _packshot(tmp_path / "d.png", bg=(240, 240, 240), box=(-10, -10, 610, 300))
    before = Image.open(p).convert("RGB").tobytes()
    _, applied = normalize_packshot(p, "neutral")
    assert not applied
    assert Image.open(p).convert("RGB").tobytes() == before
    assert not p.with_suffix(".raw.png").exists()


def test_normalization_refuses_a_low_contrast_product(tmp_path):
    """Cream upholstery on a cream cyclorama is most of an upholstery range.
    The product differs from the backdrop by fewer values than the matte can
    resolve, so the mask fragments — compositing that yields a shrunken
    product and a hard rectangle of stale backdrop. Refuse instead."""
    p = _packshot(tmp_path / "cream.png", bg=(247, 243, 234), box=(120, 150, 400, 300))
    # Product only ~12 values off the backdrop, below the solid threshold.
    img = Image.open(p).convert("RGB")
    ImageDraw.Draw(img).rectangle((120, 150, 400, 300), fill=(235, 231, 222))
    img.save(p)
    before = Image.open(p).convert("RGB").tobytes()

    _, applied = normalize_packshot(p, "neutral")
    assert not applied
    assert Image.open(p).convert("RGB").tobytes() == before


def test_normalization_refuses_a_large_hard_cast_shadow(tmp_path):
    """Legacy renders may carry a dark directional slab across the floor. The
    safe behavior is to keep the raw render, not cut that slab out as furniture."""
    p = _packshot(tmp_path / "hard-shadow.png", bg=(238, 235, 228), box=(130, 120, 430, 300))
    img = Image.open(p).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.ellipse((250, 285, 590, 400), fill=(72, 70, 68))
    draw.rectangle((130, 120, 430, 300), fill=(90, 74, 60))
    img.save(p)
    before = Image.open(p).convert("RGB").tobytes()

    _, applied = normalize_packshot(p, "neutral")
    assert not applied
    assert Image.open(p).convert("RGB").tobytes() == before


def test_normalization_never_raises_on_a_bad_file(tmp_path):
    p = tmp_path / "broken.png"
    p.write_bytes(b"not an image")
    assert normalize_packshot(p) == (p, False)
