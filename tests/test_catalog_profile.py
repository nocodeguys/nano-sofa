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
from PIL import Image, ImageDraw, ImageFilter

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_V2 = REPO_ROOT / "app-v2"
if str(APP_V2) not in sys.path:
    sys.path.insert(0, str(APP_V2))

from app.core.generator import (  # noqa: E402
    _build_prompt_text,
    _collect_reference_images,
    plan_reference_slots,
    slot_numbers,
)
from studio.normalize import (  # noqa: E402
    CATALOG_PROFILE,
    PROFILES,
    _backdrop,
    _destroys_highlight_separation,
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


def test_boucle_uses_canonical_texture_reference_without_copying_its_colour(
    server, base_image
):
    """Product, studio, and real fabric have separate visual authorities."""
    req = _request(server, base_image, catalog=True, mat="boucle")

    assert Path(req.swatch_reference_image).name == "boucle.png"
    assert req.use_swatch_for_fabric
    assert req.swatch_texture_only
    assert req.material_left_reference_image is None
    assert req.material_right_reference_image is None
    assert req.material_behavior_reference_image is None
    assert req.material_application_reference_image is None
    # 2.5-flash caps at 3 refs: base + cyclorama + macro. The colour patch
    # does not fit and must not be named in the prompt.
    assert len(_collect_reference_images(req, Image.open(base_image))) == 3
    roles = [slot.role for slot in plan_reference_slots(req)]
    assert roles == ["base_product", "scene", "material_macro"]

    text = _build_prompt_text(req)
    assert "MATERIAL TEXTURE AUTHORITY (slot 3)" in text
    assert "COLOUR AUTHORITY" not in text
    assert "IGNORE the photographed colour" in text
    assert req.upholstery_color in text
    assert "Do not copy the fold" in text
    assert "MATERIAL DOMAIN MASK" in text
    assert "Never apply it to bedding" in text
    assert "no enlarged loops" in text
    assert "do not blend visual properties across their domains" in text


def test_cremona_uses_the_supplied_canonical_texture_reference(
    server, base_image
):
    req = _request(server, base_image, catalog=True, mat="cremona")

    assert Path(req.swatch_reference_image).name == "cremona.jpg"
    assert req.use_swatch_for_fabric
    assert req.swatch_texture_only
    # The request DECLARES every curated view; the cap is applied once, in
    # plan_reference_slots, and the prompt only names attached slots.
    assert Path(req.material_behavior_reference_image).name == "cremona-behavior.jpg"
    assert Path(req.material_application_reference_image).name == "cremona-application.png"
    assert len(_collect_reference_images(req, Image.open(base_image))) == 3
    text = _build_prompt_text(req)
    assert "MATERIAL TEXTURE AUTHORITY (slot 3)" in text
    assert "MULTI-ANGLE" not in text
    assert "LIGHT-RESPONSE" not in text
    assert "IN-USE SCALE CHECK" not in text


def test_cremona_adds_light_response_reference_when_model_has_room(
    server, base_image
):
    req = _request(
        server, base_image, catalog=True, mat="cremona",
        model="gemini-3.1-flash-image", res="2K",
    )

    assert Path(req.swatch_reference_image).name == "cremona.jpg"
    assert Path(req.material_left_reference_image).name == "cremona-left.jpg"
    assert Path(req.material_right_reference_image).name == "cremona-right.jpg"
    assert Path(req.material_behavior_reference_image).name == "cremona-behavior.jpg"
    assert Path(req.material_application_reference_image).name == "cremona-application.png"
    # base, cyclorama, macro, colour patch, left, right, behaviour,
    # application = 8 attached on a 14-ref model.
    assert len(_collect_reference_images(req, Image.open(base_image))) == 8
    text = _build_prompt_text(req)
    assert "COLOUR AUTHORITY (slot 4)" in text
    assert "FABRIC MULTI-ANGLE OPTICAL AUTHORITY (slots 5 and 6)" in text
    assert "FABRIC LIGHT-RESPONSE AUTHORITY (slot 7)" in text
    assert "MATERIAL EVIDENCE HIERARCHY — HARD REQUIREMENT" in text
    assert "FABRIC IN-USE SCALE CHECK (slot 8)" in text
    assert "stable three-dimensional yarn relief" in text
    assert "do not average the two views into a smooth surface" in text
    assert "reversible directional sheen" in text
    assert "surface normal and light direction" in text
    assert "not a printed colour pattern" in text
    assert "directional grazing component" in text
    assert "tiny self-shadows" in text
    assert "delicate fuzzy rim" in text
    assert "same fine physical scale" in text
    assert "calm, continuous, finely tactile surface of the specified material" in text
    assert "must not become broad cloudy patches" in text
    assert "physical sample photographs" in text
    assert "can never override or reinterpret those samples" in text
    assert "never the reference piece's geometry" in text
    assert "Slot 1 remains the absolute product-geometry authority" in text


def test_boucle_reference_set_uses_looped_wording_not_cremona_pile(
    server, base_image, tmp_path, monkeypatch
):
    """The default slot wording describes short-pile Cremona (fine nubs, pearly
    sheen, 'calm, finely tactile at distance'); on bouclé it produced fine
    uniform grain. A full bouclé set must get the loop-specific wording."""
    import studio.request_builder as request_builder

    refs = tmp_path / "refs"
    refs.mkdir()
    for name in ("boucle", "boucle-left", "boucle-right", "boucle-behavior", "boucle-application"):
        Image.new("RGB", (64, 64), (230, 225, 215)).save(refs / f"{name}.jpg")
    monkeypatch.setattr(request_builder, "_MATERIAL_REFS_DIR", refs)

    req = _request(
        server, base_image, catalog=True, mat="boucle",
        model="gemini-3.1-flash-image", res="2K",
    )
    assert req.material_structure == "looped"
    text = _build_prompt_text(req)

    assert "FABRIC MULTI-ANGLE OPTICAL AUTHORITY (slots 5 and 6)" in text
    assert "FABRIC LIGHT-RESPONSE AUTHORITY (slot 7)" in text
    assert "FABRIC IN-USE SCALE CHECK (slot 8)" in text
    assert "coarse looped textile" in text
    assert "Preserve the same individual loops and loop clusters" in text
    assert "never forms thin sharp creases" in text
    assert "read only the looped bouclé surfaces" in text
    assert "never dissolve into fine grain" in text
    # None of the Cremona pile wording may reach a bouclé prompt.
    for cremona_phrase in (
        "fine textiles must merge into dense tactile microdetail",
        "fine nub and slub geometry",
        "pearly grazing highlights",
        "soft pearly highlights",
        "calm, continuous, finely tactile surface",
        "delicate fuzzy rim",
    ):
        assert cremona_phrase not in text, cremona_phrase


def test_catalog_backdrop_explicitly_rejects_material_reference_bleed(
    server, base_image
):
    req = _request(server, base_image, catalog=True, mat="boucle")
    text = _build_prompt_text(req)

    assert "separate physical surface from the product" in text
    assert "must not inherit, project, magnify, echo" in text
    assert "no bouclé loops" in text
    assert "SOURCE BACKGROUND DISCARD" in text
    assert "Treat every pixel outside the product silhouette" in text
    assert "Never average, blend or reconcile slot 1's background" in text


def test_material_without_canonical_swatch_gets_the_colour_patch_instead(
    server, base_image
):
    req = _request(server, base_image, catalog=True, mat="basketweave")
    assert req.swatch_reference_image is None
    roles = [slot.role for slot in plan_reference_slots(req)]
    assert roles == ["base_product", "scene", "color_patch"]
    assert len(_collect_reference_images(req, Image.open(base_image))) == 3
    text = _build_prompt_text(req)
    assert "COLOUR AUTHORITY (slot 3)" in text
    assert "#C3BEB6" in text


def test_slot_numbers_follow_attached_images_not_declared_fields(
    server, base_image, tmp_path
):
    """The audit's failure case: 3-ref model, cremona, no scene, two
    moodboards. Old code dropped the macro but still wrote 'slot 2' for it."""
    moodboards = []
    for name in ("mood-a.png", "mood-b.png"):
        path = tmp_path / name
        Image.new("RGB", (16, 16), (90, 90, 90)).save(path)
        moodboards.append(path)
    req = _request(
        server, base_image, mat="cremona", extra_reference_paths=moodboards,
    )
    plan = plan_reference_slots(req)
    roles = [slot.role for slot in plan]
    assert roles == ["base_product", "material_macro", "color_patch"]
    text = _build_prompt_text(req, slot_numbers(plan))
    assert "MATERIAL TEXTURE AUTHORITY (slot 2)" in text
    assert "COLOUR AUTHORITY (slot 3)" in text
    assert "MULTI-ANGLE" not in text
    assert "moodboard" not in text.lower() or "REFERENCE LOCK" not in text


def test_locked_moodboard_outranks_material_views(server, base_image, tmp_path):
    mood = tmp_path / "mood.png"
    Image.new("RGB", (16, 16), (90, 90, 90)).save(mood)
    req = _request(
        server, base_image, mat="cremona", extra_reference_paths=[mood],
        lock_to_reference=True,
    )
    roles = [slot.role for slot in plan_reference_slots(req)]
    assert roles == ["base_product", "extra_reference_1", "material_macro"]
    assert "REFERENCE LOCK" in _build_prompt_text(req)


def test_dark_colours_get_the_deep_shade_clause_and_light_ones_do_not(
    server, base_image
):
    dark = _request(server, base_image, color="velutto-27")
    assert dark.upholstery_hex == "#122D24"
    assert dark.color_id == "velutto-27"
    assert dark.fabric_code == "Velutto 27"
    assert "DEEP-SHADE EXPOSURE" in _build_prompt_text(dark)

    light = _request(server, base_image, color="pearl")
    assert "DEEP-SHADE EXPOSURE" not in _build_prompt_text(light)


def test_custom_colour_hex_is_recovered_for_the_patch(server, base_image):
    req = _request(
        server, base_image, color="custom",
        color_custom="dusty terracotta (exact upholstery colour hex #b5674d)",
    )
    assert req.upholstery_hex == "#B5674D"
    assert req.color_id == "custom"
    assert "color_patch" in [s.role for s in plan_reference_slots(req)]


def test_white_bedding_exposure_rule_is_bed_only(server, base_image):
    bed = _request(server, base_image, kind="bed", catalog=True)
    sofa = _request(server, base_image, kind="sofa", size="3", catalog=True)
    assert "WHITE-TEXTILE EXPOSURE" in _build_prompt_text(bed)
    assert "WHITE-TEXTILE EXPOSURE" not in _build_prompt_text(sofa)


def test_variant_scene_that_contains_the_product_is_never_called_empty(
    server, base_image
):
    from dataclasses import replace

    req = _request(
        server, base_image, env="cyclorama_neutral", env_mode="",
        scene_image_path=base_image,
    )
    honest = replace(req, scene_contains_product=True)
    text = _build_prompt_text(honest)
    assert "EMPTY studio plate" not in text
    assert "DIFFERENT upholstery colour" in text
    assert "EMPTY studio plate" in _build_prompt_text(req)


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


def test_pale_profiles_keep_the_bottom_catalog_band_consistent(tmp_path):
    """The empty floor should converge without a hard pasted-on strip."""
    a = _packshot(tmp_path / "warm.png", bg=(246, 239, 224), box=(105, 150, 390, 330))
    b = _packshot(tmp_path / "cool.png", bg=(229, 235, 241), box=(190, 125, 510, 320))
    normalize_packshot(a, "ivory")
    normalize_packshot(b, "ivory")

    arr_a = np.asarray(Image.open(a).convert("RGB"))
    arr_b = np.asarray(Image.open(b).convert("RGB"))
    y = round(arr_a.shape[0] * 0.95)
    assert np.abs(arr_a[y:].astype(int) - arr_b[y:].astype(int)).mean() <= 2.0

    # No abrupt seam near either of the old 8/95-percent hard-lock boundaries.
    for arr in (arr_a, arr_b):
        col = arr[:, 8].astype(int)
        assert np.abs(np.diff(col, axis=0)).max() <= 2


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


def test_textile_recovery_respects_subject_domain_mask():
    """Noise in a weak reference must never be enhanced on the studio wall."""
    yy, xx = np.mgrid[0:180, 0:240]
    faint_wall = 244 + np.rint(1.8 * np.sin(xx / 5.0) * np.sin(yy / 7.0))
    arr = np.repeat(faint_wall[..., None], 3, axis=2).astype(np.uint8)
    src = Image.fromarray(arr, "RGB")

    out = np.asarray(
        _recover_pale_textile_detail(src, np.zeros((180, 240, 1), dtype=np.float32))
    )

    assert np.array_equal(out, arr)


def test_highlight_guard_detects_a_blown_pale_subject_band():
    """A global lift must not turn textured ivory upholstery into white mass."""
    h, w = 450, 600
    before = np.full((h, w, 3), (232, 229, 224), dtype=np.uint8)
    yy, xx = np.mgrid[0:210, 0:420]
    textile = 239 + np.rint(4.0 * np.sin(xx / 7.0) + 2.0 * np.sin(yy / 5.0))
    before[145:355, 90:510] = np.clip(textile[..., None], 0, 255).astype(np.uint8)
    after = np.clip(before.astype(np.int16) + 16, 0, 255).astype(np.uint8)

    assert _destroys_highlight_separation(
        Image.fromarray(before, "RGB"), Image.fromarray(after, "RGB")
    )


def test_highlight_guard_accepts_a_small_colour_calibration():
    before = Image.new("RGB", (600, 450), (240, 237, 231))
    after = Image.new("RGB", (600, 450), (244, 242, 238))
    assert not _destroys_highlight_separation(before, after)


def test_ivory_normalization_locks_background_without_blowing_pale_product(tmp_path):
    p = tmp_path / "pale-bed.png"
    arr = np.full((450, 600, 3), (228, 226, 222), dtype=np.uint8)
    yy, xx = np.mgrid[0:210, 0:420]
    textile = 239 + np.rint(4.0 * np.sin(xx / 7.0) + 2.0 * np.sin(yy / 5.0))
    arr[145:355, 90:510] = np.clip(textile[..., None], 0, 255).astype(np.uint8)
    Image.fromarray(arr, "RGB").save(p)
    before = arr.astype(np.float32)

    _, applied = normalize_packshot(p, "ivory")

    assert applied
    after = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)
    before_textile = before[145:355, 90:510].mean(axis=2)
    after_textile = after[145:355, 90:510].mean(axis=2)
    assert float((after_textile - before_textile).mean()) <= 3.5
    assert float((after_textile > 248.0).mean()) <= float(
        (before_textile > 248.0).mean()
    ) + 0.02
    assert np.allclose(after[0, 6], PROFILES["ivory"].top_rgb, atol=2)
    assert p.with_suffix(".raw.png").exists()


def test_selective_calibration_suppresses_faint_backdrop_texture(tmp_path):
    """A detailed correction mask must never become visible on a smooth wall.

    Regression for the real bouclé run where an almost imperceptible residual
    in Gemini's raw backdrop became a huge fabric-like stencil after the
    background correction was blended through a pixel-detailed alpha mask.
    """
    p = tmp_path / "faint-backdrop-pattern.png"
    h, w = 450, 600
    yy, xx = np.mgrid[0:h, 0:w]
    faint = 228.0 + 2.4 * np.sin(xx / 17.0) * np.sin(yy / 23.0)
    arr = np.repeat(faint[..., None], 3, axis=2)
    arr[185:350, 135:465] = (104, 92, 80)
    Image.fromarray(np.clip(arr + 0.5, 0, 255).astype(np.uint8), "RGB").save(p)

    _, applied = normalize_packshot(p, "ivory")

    assert applied
    after = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)
    # Empty wall above the product may keep a trace of the model's native wash,
    # but the correction must not amplify it into visible relief.
    before_wall = arr[80:165, 45:555, 0]
    after_wall = after[80:165, 45:555, 0]
    before_smooth = np.asarray(
        Image.fromarray(before_wall.astype(np.uint8)).filter(ImageFilter.GaussianBlur(8))
    ).astype(np.float32)
    after_smooth = np.asarray(
        Image.fromarray(after_wall.astype(np.uint8)).filter(ImageFilter.GaussianBlur(8))
    ).astype(np.float32)
    before_residual = np.abs(before_wall - before_smooth).mean()
    after_residual = np.abs(after_wall - after_smooth).mean()
    assert float(after_residual) <= float(before_residual) * 0.70


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
