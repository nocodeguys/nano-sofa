"""Deterministic packshot normalization.

The generative side (cyclorama profiles + the catalog framing contract) gets
every render *close* to the same look, but a diffusion model will never land
on the same backdrop RGB or the same subject scale twice. For a catalog grid
that reads as one photo session, "close" is not enough — the eye picks up a
two-percent difference in background tone across adjacent tiles instantly.

So after the render lands we normalize it deterministically.  Pale brand
profiles use a safe whole-frame calibration: estimate the source cyclorama's
smooth two-axis light field, subtract it, then add the canonical profile field.
That changes only low-frequency colour/exposure and keeps every product edge,
fabric detail and natural contact shadow intact.  The neutral marketplace
profile can still use the stricter matte/rescale/composite path because a white
or isolated product is not its primary use case.

Everything here is pure Pillow + numpy; no model call, no network.

The normalized image replaces the master, deliberately: every downstream
consumer (delivery-format derivation, the variant pixel-lock chain, the
catalog anchor) keys off `result.output_path`, and all of them should inherit
the normalized look rather than the raw render. The untouched render is kept
beside it as `<stem>.raw.png` so a rejected matte can always be diagnosed
against the original.

The strict matte path is deliberately conservative: when the mask looks implausible
(product touching the frame edge, absurd coverage) we return the master
untouched and log why, rather than shipping a mangled render.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from studio.paths import logger


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PackshotProfile:
    """The geometric + tonal contract every catalog packshot is forced onto.

    `width_frac` / `height_frac` define a safe box: the product is scaled to
    fit inside it preserving its own aspect, so a tall continental bed and a
    low platform bed end up with the same visual weight instead of the same
    literal width. `baseline_frac` is where the product's bottom edge sits,
    measured from the top of the canvas — locking it is what stops the floor
    line from jumping between tiles in a grid.

    The backdrop is rebuilt, not flat-filled. A single flat colour is the one
    thing that reliably makes a packshot look like a cutout pasted onto paper:
    real cycloramas carry a soft vertical wash from the key light. `top_rgb`,
    `background` and `floor_rgb` are the tones at the top edge, at the product's
    baseline, and at the bottom edge; the pass interpolates between them.
    """

    name: str = "neutral"
    label: str = "Neutralna biel"

    background: tuple[int, int, int] = (250, 250, 250)   # tone at the baseline
    top_rgb: tuple[int, int, int] = (255, 255, 255)      # tone at the top edge
    floor_rgb: tuple[int, int, int] = (250, 250, 250)    # tone at the bottom edge

    # Optional four-corner light field. Most catalog profiles only need the
    # vertical wash above, but a real lit cyclorama can carry a strong lateral
    # component as well. When all four values are present `_backdrop` uses a
    # bilinear two-axis gradient instead of the vertical three-stop wash.
    top_left_rgb: Optional[tuple[int, int, int]] = None
    top_right_rgb: Optional[tuple[int, int, int]] = None
    floor_left_rgb: Optional[tuple[int, int, int]] = None
    floor_right_rgb: Optional[tuple[int, int, int]] = None

    # A tiny fixed grain keeps the directional atelier profile photographic
    # rather than digitally flat. The RNG is seeded from the canvas dimensions,
    # so two renders at the same size receive identical backdrop pixels.
    grain_strength: float = 0.0

    # Directional/editorial profiles favor preserving the model's native
    # product edges and shadow over aggressive cut-out/rescaling. In this mode
    # only confidently identified backdrop pixels are repainted. The numeric
    # prompt contract still controls scale and baseline.
    repaint_only: bool = False

    # Safest finishing path for pale upholstery: calibrate the whole photograph
    # against the profile's smooth studio field.  This preserves every product
    # edge and the model's natural contact shadow — no semantic cut-out needed.
    calibrate_only: bool = False

    width_frac: float = 0.82
    height_frac: float = 0.70
    baseline_frac: float = 0.88

    # Synthesized contact shadow. `offset_frac` shifts it sideways as a
    # fraction of the product's width — a key light that is off to one side
    # throws the shadow to the other, and a shadow sitting dead centre under
    # a side-lit product is what makes a render read as fake.
    shadow_rgb: tuple[int, int, int] = (210, 210, 210)
    shadow_alpha: int = 90           # peak alpha before blur, 0-255
    shadow_width_frac: float = 0.94  # of the product's own width
    shadow_height_frac: float = 0.07  # of the product's own width
    shadow_offset_frac: float = 0.0

    # Gentle output-referred highlight roll-off applied to the isolated
    # product only.  Image models often push white bedding to RGB 255 in a
    # bright studio; compressing just the last part of the curve restores
    # separation from an off-white backdrop without greying normal midtones.
    highlight_knee: int = 245
    highlight_ceiling: int = 250

    # Matte tolerances, in 0-255 max-channel distance from the row backdrop.
    tol_lo: int = 10   # below this a pixel is pure background
    tol_hi: int = 26   # above this a pixel is pure product
    tol_solid: int = 34  # geometry threshold — excludes the baked soft shadow


# Named profiles, each paired with the cyclorama prompt profile that describes
# the same look to the model (see _CATALOG_PROFILE_ENV in studio/mappings.py).
# The render lands close; this pass makes it exact.
PROFILES: dict[str, PackshotProfile] = {
    # Pure photo-studio white. Clinical and completely neutral — the safe
    # choice for marketplaces that composite product shots onto their own
    # backgrounds, and the wrong choice for a warm interiors brand.
    "neutral": PackshotProfile(
        name="neutral",
        label="Neutralna biel — #FAFAFA",
        shadow_alpha=34,
        shadow_width_frac=0.82,
        shadow_height_frac=0.028,
    ),
    # Warm architectural ivory with the key light at the top-left: the floor
    # in front of the product is the brightest zone, the top of the backdrop
    # softens a few values, and the shadow feathers to the right. This is the
    # warm-catalog / interiors-brand look.
    "ivory": PackshotProfile(
        name="ivory",
        label="Naturalna kość słoniowa — #F7F5F1",
        background=(247, 245, 241),
        top_rgb=(244, 242, 238),
        floor_rgb=(250, 249, 246),
        calibrate_only=True,
        shadow_rgb=(208, 205, 199),
        shadow_alpha=38,
        shadow_width_frac=0.82,
        shadow_height_frac=0.028,
        shadow_offset_frac=0.02,
    ),
    # Bright airy off-white with a barely-there warm undertone and almost no
    # gradient. Lifted and editorial without going stark.
    "paperwhite": PackshotProfile(
        name="paperwhite",
        label="Jasna biel papierowa — #FCFAF7",
        background=(252, 250, 247),
        top_rgb=(250, 248, 245),
        floor_rgb=(254, 252, 250),
        calibrate_only=True,
        shadow_rgb=(214, 208, 199),
        shadow_alpha=30,
        shadow_width_frac=0.80,
        shadow_height_frac=0.025,
        shadow_offset_frac=0.015,
    ),
    # Measured from the user's furniture-studio reference: a genuine lit
    # cyclorama rather than a flat packshot field. It is darker/olive at the
    # upper-left and opens into a pale blush at the lower-right.
    "atelier": PackshotProfile(
        name="atelier",
        label="Atelier — ciepły gradient",
        background=(220, 214, 209),
        top_rgb=(181, 174, 162),
        floor_rgb=(220, 214, 209),
        top_left_rgb=(168, 162, 146),       # #A8A292
        top_right_rgb=(193, 185, 176),      # #C1B9B0
        floor_left_rgb=(195, 189, 180),     # #C3BDB4
        floor_right_rgb=(238, 231, 231),    # #EEE7E7
        grain_strength=0.8,
        calibrate_only=True,
        shadow_rgb=(157, 149, 136),
        shadow_alpha=36,
        shadow_width_frac=0.80,
        shadow_height_frac=0.026,
        shadow_offset_frac=-0.015,
    ),
    # Measured from the Westwing-style bed grid supplied by the user. The outer
    # field is consistently #FAF8F6; perceived variation comes from the bed's
    # own soft contact shadow, not from a changing wall colour.
    "softblush": PackshotProfile(
        name="softblush",
        label="Pudrowy krem — #FAF8F6",
        background=(250, 248, 246),
        top_rgb=(250, 248, 246),
        floor_rgb=(250, 248, 246),
        calibrate_only=True,
        shadow_rgb=(211, 205, 199),
        shadow_alpha=72,
        shadow_width_frac=0.98,
        shadow_height_frac=0.065,
        shadow_offset_frac=0.02,
    ),
}

DEFAULT_PROFILE = "ivory"


def resolve_profile(name: str | None) -> PackshotProfile:
    """Profile by id, falling back to the default for anything unknown."""
    return PROFILES.get((name or "").strip().lower(), PROFILES[DEFAULT_PROFILE])


CATALOG_PROFILE = PROFILES[DEFAULT_PROFILE]

# Suffix of the untouched render kept beside every normalized master. Anything
# listing the outputs directory must skip these or each catalog shot shows up
# twice.
RAW_SUFFIX = ".raw.png"


def is_raw_copy(path: Path) -> bool:
    """True for the pre-normalization copy kept beside a normalized master."""
    return path.name.endswith(RAW_SUFFIX)

# ---------------------------------------------------------------------------
# Backdrop estimation + matting
# ---------------------------------------------------------------------------
def _background_surface(arr: np.ndarray) -> np.ndarray:
    """Estimate a smooth 2-D cyclorama light field from the frame border.

    The old per-row median assumed that every backdrop varied only vertically.
    A side-lit cyclorama (and many real Gemini renders) also varies strongly
    left-to-right; subtracting a one-dimensional estimate classified that
    lateral wash as product and pasted a rectangle of stale background around
    the furniture. A robust quadratic surface captures vertical, lateral and
    diagonal light while deliberately ignoring local product/shadow detail.
    """
    h, w = arr.shape[:2]
    strip = max(8, int(min(h, w) * 0.04))
    step = max(1, max(h, w) // 512)

    y_lr = np.arange(0, h, step)
    x_lr = np.r_[np.arange(0, strip, step), np.arange(max(0, w - strip), w, step)]
    yy_lr, xx_lr = np.meshgrid(y_lr, x_lr, indexing="ij")

    y_tb = np.r_[np.arange(0, strip, step), np.arange(max(0, h - strip), h, step)]
    x_tb = np.arange(0, w, step)
    yy_tb, xx_tb = np.meshgrid(y_tb, x_tb, indexing="ij")

    ys = np.concatenate([yy_lr.ravel(), yy_tb.ravel()])
    xs = np.concatenate([xx_lr.ravel(), xx_tb.ravel()])
    xn = xs.astype(np.float64) / max(1, w - 1)
    yn = ys.astype(np.float64) / max(1, h - 1)
    design = np.column_stack((
        np.ones_like(xn), xn, yn, xn * yn, xn * xn, yn * yn,
    ))
    values = arr[ys, xs, :].astype(np.float64)

    coeff, *_ = np.linalg.lstsq(design, values, rcond=None)
    # One robust refit drops edge-touching product pixels, dark dust and the
    # occasional shadow that reaches the bottom border.
    residual = np.max(np.abs(values - design @ coeff), axis=1)
    keep = residual <= np.quantile(residual, 0.85)
    if int(keep.sum()) >= 24:
        coeff, *_ = np.linalg.lstsq(design[keep], values[keep], rcond=None)

    x = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :, None]
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
    c = coeff.astype(np.float32)
    return (
        c[0] + c[1] * x + c[2] * y + c[3] * x * y
        + c[4] * x * x + c[5] * y * y
    )


def _border_connected(bg: np.ndarray, max_iter: int = 4096) -> np.ndarray:
    """Background pixels reachable from the frame edge (morphological
    reconstruction by dilation, 4-connected).

    Runs on a downscaled mask — connectivity only needs to be topologically
    right, and a full-resolution flood fill in Python would dominate the
    request. Anything NOT reached is product, which is what fills interior
    holes where the product's own tone matches the backdrop.
    """
    marker = np.zeros_like(bg)
    marker[0, :] = bg[0, :]
    marker[-1, :] = bg[-1, :]
    marker[:, 0] = bg[:, 0]
    marker[:, -1] = bg[:, -1]

    for _ in range(max_iter):
        grown = marker.copy()
        grown[1:, :] |= marker[:-1, :]
        grown[:-1, :] |= marker[1:, :]
        grown[:, 1:] |= marker[:, :-1]
        grown[:, :-1] |= marker[:, 1:]
        grown &= bg
        if np.array_equal(grown, marker):
            break
        marker = grown
    return marker


def _downscale_mask(mask: np.ndarray, target: int = 384) -> tuple[np.ndarray, tuple[int, int]]:
    """Shrink a boolean mask for the connectivity pass; returns (small, size)."""
    h, w = mask.shape
    if max(h, w) <= target:
        return mask, (w, h)
    scale = target / max(h, w)
    sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
    img = Image.fromarray((mask * 255).astype(np.uint8)).resize((sw, sh), Image.BILINEAR)
    return np.asarray(img) > 127, (sw, sh)


def _despeckle(solid: np.ndarray, radius: int = 2) -> np.ndarray:
    """Morphological opening — drops specks thinner than the kernel.

    Gemini renders routinely carry a few stray pixels near a frame corner.
    Left in, a single speck stretches the bounding box across the whole frame,
    which silently shrinks every product and pushes it off the baseline. The
    opening runs through Pillow's C filters, so it costs about a millisecond
    even at 4K.
    """
    k = radius * 2 + 1
    img = Image.fromarray((solid * 255).astype(np.uint8))
    img = img.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k))
    return np.asarray(img) > 127


def _main_component(solid: np.ndarray) -> np.ndarray:
    """Keep only the connected blob that holds the product.

    A morphological opening removes single-pixel dust but not the slightly
    larger artifacts Gemini sometimes leaves near a frame corner, and one such
    artifact stretches the bounding box across the whole frame. Connectivity is
    the reliable discriminator: seed from the solid pixel nearest the mask's
    centroid — packshot products are centred, artifacts are not — and grow.

    Anything dropped is reported. If the discarded area is more than a twentieth
    of the blob we keep, this is not dust and we refuse to guess: the caller
    gets the untouched mask back so a genuinely two-part product is never
    silently cropped in half.
    """
    small, _ = _downscale_mask(solid)
    if not small.any():
        return solid

    ys, xs = np.nonzero(small)
    cy, cx = ys.mean(), xs.mean()
    nearest = np.argmin((ys - cy) ** 2 + (xs - cx) ** 2)

    marker = np.zeros_like(small)
    marker[ys[nearest], xs[nearest]] = True
    for _ in range(4096):
        grown = marker.copy()
        grown[1:, :] |= marker[:-1, :]
        grown[:-1, :] |= marker[1:, :]
        grown[:, 1:] |= marker[:, :-1]
        grown[:, :-1] |= marker[:, 1:]
        grown &= small
        if np.array_equal(grown, marker):
            break
        marker = grown

    kept, total = int(marker.sum()), int(small.sum())
    dropped = total - kept
    if dropped == 0:
        return solid
    if dropped > kept * 0.05:
        logger.warning(
            "Product mask has %d detached pixel(s) against %d in the main blob "
            "— too large to treat as an artifact, keeping the full mask.",
            dropped, kept,
        )
        return solid

    h, w = solid.shape
    comp = np.asarray(
        Image.fromarray((marker * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)
    ) > 100
    logger.info("Dropped %d detached mask pixel(s) as render artifacts.", dropped)
    return solid & comp


def _bbox(solid: np.ndarray) -> Optional[tuple[int, int, int, int]]:
    """Tight bbox (l, t, r, b) of the already-despeckled solid mask."""
    cols = solid.any(axis=0)
    rows = solid.any(axis=1)
    if not cols.any() or not rows.any():
        return None
    xs = np.where(cols)[0]
    ys = np.where(rows)[0]
    return int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1


def _product_alpha(
    arr: np.ndarray, prof: PackshotProfile
) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Return (alpha, solid, background) masks or None if matting failed.

    `alpha` is a soft matte used for compositing — the ramp between tol_lo and
    tol_hi keeps antialiased product edges smooth and drives the model's faint
    baked contact shadow toward zero. `solid` is the strict-threshold mask used
    for geometry (bbox), so the baked shadow does not inflate the bounding box
    and throw off scale and baseline.
    """
    h, w = arr.shape[:2]
    bg_surface = _background_surface(arr)              # (H, W, 3)
    diff = np.abs(arr - bg_surface)                    # (H, W, 3)
    dist = diff.max(axis=2)                            # (H, W)

    # Background candidates, then keep only the frame-connected component so
    # that same-tone regions enclosed by the product stay product.
    # Use the solid threshold for flood-fill connectivity. Requiring the old
    # `tol_lo` exact match left every modest hotspot/gradient residual outside
    # the background component, even though it was visibly still backdrop.
    bg_candidates = dist <= prof.tol_solid

    # A cast shadow can be far darker than the fitted backdrop while retaining
    # almost exactly its chromaticity (the RGB proportions stay the same). On
    # real renders that shadow was previously taken for furniture and survived
    # as a large jagged slab. Extend the floor-background candidates with pixels
    # that are merely darkened backdrop. Restrict this to the lower half so a
    # neutral/cream headboard cannot be swallowed by the rule.
    rgb_sum = np.maximum(arr.sum(axis=2, keepdims=True), 1.0)
    bg_sum = np.maximum(bg_surface.sum(axis=2, keepdims=True), 1.0)
    chroma_dist = np.max(np.abs(arr / rgb_sum - bg_surface / bg_sum), axis=2) * 255.0
    luma = arr.mean(axis=2)
    bg_luma = bg_surface.mean(axis=2)
    floor_zone = np.arange(h, dtype=np.float32)[:, None] >= h * 0.52
    channel_spread = arr.max(axis=2) - arr.min(axis=2)

    # A large, dark, nearly neutral floor region is a hard model-rendered cast
    # shadow. Without semantic segmentation it cannot be separated reliably
    # from neutral furniture, and attempting to do so creates the ragged slabs
    # seen in the original normalizer. New catalog prompts ask for a restrained
    # contact shadow; reject old/hard-shadow renders and keep their raw master
    # untouched instead of shipping a visibly damaged composite.
    hard_cast_shadow = (
        floor_zone
        & (luma < bg_luma - 70.0)
        & (channel_spread <= 12.0)
    )
    if float(hard_cast_shadow.mean()) > 0.005 and not prof.repaint_only:
        logger.warning(
            "Packshot matte rejected: a strong neutral cast shadow covers %.1f%% "
            "of the frame; safe separation would damage the product edge.",
            float(hard_cast_shadow.mean()) * 100,
        )
        return None

    shadow_like = (
        floor_zone
        & (chroma_dist <= 3.5)
        & (luma < bg_luma - prof.tol_solid)
    )
    if prof.repaint_only:
        # Repaint mode never cuts or moves the product, so it can safely treat
        # a clearly neutral floor cast as replaceable studio. Connectivity still
        # prevents isolated dark product parts from being swallowed.
        shadow_like |= hard_cast_shadow
    bg_candidates |= shadow_like
    small, (sw, sh) = _downscale_mask(bg_candidates)
    reached_small = _border_connected(small)
    reached = np.asarray(
        Image.fromarray((reached_small * 255).astype(np.uint8)).resize((w, h), Image.BILINEAR)
    ) > 127
    background = bg_candidates & reached

    ramp = np.clip((dist - prof.tol_lo) / max(1, prof.tol_hi - prof.tol_lo), 0.0, 1.0)
    solid = _main_component(_despeckle((dist > prof.tol_solid) & ~background))

    # The alpha ramp is allowed only in a narrow dilation of the real product
    # mask. This is the second guard against carrying a rectangular patch of
    # old cyclorama inside the crop box when the source has a local hotspot.
    radius = max(2, min(7, round(max(h, w) * 0.002)))
    kernel = radius * 2 + 1
    support = np.asarray(
        Image.fromarray((solid * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(kernel))
    ) > 0
    alpha = np.where(support & ~background, ramp, 0.0).astype(np.float32)
    # Feather by roughly one output pixel. The color-distance ramp handles most
    # antialiasing; this removes the last stair-step introduced by morphology.
    alpha_img = Image.fromarray((alpha * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(max(0.6, max(h, w) * 0.0007))
    )
    alpha = np.asarray(alpha_img).astype(np.float32) / 255.0

    # Low-contrast guard. A cream product on a cream cyclorama — the core of
    # most upholstery ranges — differs from the backdrop by fewer values than
    # the solid threshold, so the mask comes back as scattered fragments
    # rather than a silhouette. Compositing that produces a shrunken product
    # and a hard rectangle of stale backdrop where the crop box was. The tell
    # is a mask that fills only a small part of its own bounding box: a real
    # product silhouette fills a good half of it.
    span = _bbox(solid)
    if span is not None:
        l, t, r, b = span
        box_area = max(1, (r - l) * (b - t))
        fill = float(solid.sum()) / box_area
        if fill < 0.25 and not prof.repaint_only:
            logger.warning(
                "Packshot matte rejected: product fills only %.0f%% of its own "
                "bounding box — too little contrast against the backdrop to cut "
                "it out reliably. Leaving the render untouched.", fill * 100
            )
            return None

    coverage = float(solid.mean())
    if not prof.repaint_only and not (0.02 <= coverage <= 0.92):
        logger.warning(
            "Packshot matte rejected: product covers %.1f%% of the frame "
            "(expected 2-92%%) — leaving the render untouched.", coverage * 100
        )
        return None

    # A product bleeding off the frame edge means this is a crop / detail /
    # lifestyle shot, not a hero packshot. Rescaling it would be wrong.
    edge_touch = (
        solid[0, :].mean() + solid[-1, :].mean() + solid[:, 0].mean() + solid[:, -1].mean()
    ) / 4
    if edge_touch > 0.02 and not prof.repaint_only:
        logger.warning(
            "Packshot matte rejected: product touches the frame edge (%.1f%%) "
            "— looks like a crop, not a hero packshot.", edge_touch * 100
        )
        return None

    return alpha, solid, background


# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------
def _backdrop(size: tuple[int, int], prof: PackshotProfile) -> Image.Image:
    """Rebuild the cyclorama as a soft vertical wash.

    A flat fill is the giveaway that a packshot was composited: a real
    cyclorama is lit, so it carries a gentle gradient from the key light. The
    profile gives three tones — top edge, product baseline, bottom edge — and
    this interpolates between them with the baseline as the knee, which is
    also where the eye reads the floor starting.

    The whole range spans a handful of RGB values. It should be felt, not seen.
    """
    w, h = size
    corners = (
        prof.top_left_rgb, prof.top_right_rgb,
        prof.floor_left_rgb, prof.floor_right_rgb,
    )
    if all(corner is not None for corner in corners):
        tl, tr, bl, br = (np.array(corner, dtype=np.float32) for corner in corners)
        x = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :, None]
        y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
        upper = tl[None, None, :] * (1.0 - x) + tr[None, None, :] * x
        lower = bl[None, None, :] * (1.0 - x) + br[None, None, :] * x
        field = upper * (1.0 - y) + lower * y
    else:
        knee = max(1, min(h - 1, round(h * prof.baseline_frac)))
        top = np.array(prof.top_rgb, dtype=np.float32)
        base = np.array(prof.background, dtype=np.float32)
        floor = np.array(prof.floor_rgb, dtype=np.float32)

        rows = np.empty((h, 3), dtype=np.float32)
        upper_t = np.linspace(0.0, 1.0, knee, endpoint=False)[:, None]
        rows[:knee] = top + (base - top) * upper_t
        lower_t = np.linspace(0.0, 1.0, h - knee)[:, None]
        rows[knee:] = base + (floor - base) * lower_t
        field = np.repeat(rows[:, None, :], w, axis=1)

    if prof.grain_strength > 0:
        rng = np.random.default_rng(20260827 + w * 17 + h * 31)
        grain = rng.normal(0.0, prof.grain_strength, (h, w, 1)).astype(np.float32)
        field = field + grain
    return Image.fromarray(np.clip(field + 0.5, 0, 255).astype(np.uint8), "RGB")


def _rolloff_highlights(src: Image.Image, prof: PackshotProfile) -> Image.Image:
    """Compress only the last stop of highlights; leave all midtones intact."""
    arr = np.asarray(src.convert("RGB")).astype(np.float32)
    knee = float(max(0, min(254, prof.highlight_knee)))
    ceiling = float(max(int(knee) + 1, min(255, prof.highlight_ceiling)))
    if ceiling >= 255:
        return src.convert("RGB")
    scale_hi = (ceiling - knee) / (255.0 - knee)
    arr = np.where(arr > knee, knee + (arr - knee) * scale_hi, arr)
    return Image.fromarray(np.clip(arr + 0.5, 0, 255).astype(np.uint8), "RGB")


def _recover_pale_textile_detail(src: Image.Image) -> Image.Image:
    """Restore restrained local contrast in bright, textured textile areas.

    A global exposure change would ruin the now-stable ivory cyclorama. Instead
    this pass reacts only where a pale, nearly neutral area contains real
    high-frequency structure (weave, seams or folds). A smooth background has
    no local detail and receives a zero mask, so its canonical pixels stay
    untouched. This cannot invent detail that the model clipped completely;
    the prompt contract prevents that upstream, while this pass protects the
    subtle structure that survives.
    """
    rgb = src.convert("RGB")
    arr = np.asarray(rgb).astype(np.float32)
    radius = max(5.0, min(rgb.size) * 0.012)
    low = np.asarray(rgb.filter(ImageFilter.GaussianBlur(radius))).astype(np.float32)
    high = arr - low

    lum = arr[..., 0] * 0.2126 + arr[..., 1] * 0.7152 + arr[..., 2] * 0.0722
    chroma = arr.max(axis=2) - arr.min(axis=2)
    detail_energy = np.mean(np.abs(high), axis=2)

    pale = np.clip((lum - 222.0) / 20.0, 0.0, 1.0)
    neutral = np.clip((24.0 - chroma) / 14.0, 0.0, 1.0)
    textured = np.clip((detail_energy - 0.25) / 2.2, 0.0, 1.0)
    mask = (pale * neutral * textured)[..., None]

    # Strengthen existing folds/weave and pull only their broadest bright
    # peaks down a few values. The result remains white, but no longer reads
    # as one clipped featureless mass.
    peak = np.clip((lum - 240.0) * 0.32, 0.0, 4.0)[..., None]
    # Deepen only the negative side of the local signal. Bright threads never
    # get brighter (important near clipping), while folds and weave valleys
    # regain enough separation to read at catalog-tile size.
    recovered = arr + np.minimum(high, 0.0) * (1.8 * mask) - peak * (0.35 * mask)
    return Image.fromarray(np.clip(recovered + 0.5, 0, 255).astype(np.uint8), "RGB")


def _compose(
    src: Image.Image, alpha: np.ndarray, box: tuple[int, int, int, int], prof: PackshotProfile
) -> Image.Image:
    """Place the matted product on a fresh backdrop at the profile's geometry."""
    w, h = src.size
    l, t, r, b = box
    pw, ph = r - l, b - t

    # Fit the product into the safe box, preserving its own aspect ratio.
    scale = min((w * prof.width_frac) / pw, (h * prof.height_frac) / ph)
    nw, nh = max(1, round(pw * scale)), max(1, round(ph * scale))

    cut = _rolloff_highlights(
        src.crop(box).convert("RGB").resize((nw, nh), Image.LANCZOS), prof
    )
    cut_a = Image.fromarray((alpha[t:b, l:r] * 255).astype(np.uint8)).resize((nw, nh), Image.LANCZOS)

    left = round((w - nw) / 2)
    top = round(h * prof.baseline_frac) - nh

    canvas = _backdrop((w, h), prof)

    # Synthetic contact shadow — one restrained ellipse, one blur, identical maths for
    # every product, which is the whole point: the shadow stops being a
    # per-render variable. The sideways offset follows the profile's key
    # light, so a warm side-lit backdrop doesn't get a shadow sitting dead
    # centre under the product like a sticker.
    sw = max(2, round(nw * prof.shadow_width_frac))
    sh = max(2, round(nw * prof.shadow_height_frac))
    blur = max(2.0, w * 0.012)
    sx = left + (nw - sw) // 2 + round(nw * prof.shadow_offset_frac)
    shadow_a = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shadow_a).ellipse(
        [sx, top + nh - sh // 2, sx + sw, top + nh + sh // 2],
        fill=prof.shadow_alpha,
    )
    shadow_a = shadow_a.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(Image.new("RGB", (w, h), prof.shadow_rgb), (0, 0), shadow_a)

    canvas.paste(cut, (left, top), cut_a)
    return canvas


def _repaint_background(
    src: Image.Image, background: np.ndarray, prof: PackshotProfile
) -> Image.Image:
    """Replace only confidently identified backdrop pixels.

    This is the safe path for editorial gradients and very pale products. It
    deliberately preserves the model-rendered product, contact shadow and edge
    antialiasing in place, while making the surrounding studio field exactly
    repeatable. A tiny feather prevents a visible boundary where the strict
    background mask meets the product/shadow integration zone.
    """
    target = _backdrop(src.size, prof)
    protected = _rolloff_highlights(src, prof)
    mask = Image.fromarray((background * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(max(0.8, max(src.size) * 0.0008))
    )
    return Image.composite(target, protected, mask)


def _calibrate_field(src: Image.Image, prof: PackshotProfile) -> Image.Image:
    """Relight the complete photograph onto the profile without cutting it out.

    The source border gives us the model's smooth cyclorama light field.  The
    difference between that field and the canonical field is a low-frequency
    colour/exposure correction which can be applied to the whole photograph.
    Product shading and the native contact shadow remain relative to the floor,
    while the studio palette becomes repeatable and pale edges cannot be eaten
    by a matte.
    """
    arr = np.asarray(src.convert("RGB")).astype(np.float32)
    source_field = _background_surface(arr)
    target_field = np.asarray(_backdrop(src.size, prof)).astype(np.float32)
    correction = np.clip(target_field - source_field, -72.0, 72.0)
    calibrated = Image.fromarray(
        np.clip(arr + correction + 0.5, 0, 255).astype(np.uint8), "RGB"
    )
    finished = _recover_pale_textile_detail(_rolloff_highlights(calibrated, prof))

    # The upper and lower edges are guaranteed empty space in the catalog
    # framing contract. Lock those bands to the canonical studio plate after
    # calibration so a grid never shows a changing strip of floor at its
    # bottom edge. The feather begins well below the product baseline/contact
    # shadow and prevents a visible seam. This is intentionally not a product
    # matte: no semantic edge or shadow pixels around the furniture are cut.
    out = np.asarray(finished).astype(np.float32).copy()
    target = np.asarray(_rolloff_highlights(_backdrop(src.size, prof), prof)).astype(np.float32)
    h = out.shape[0]

    top_full = max(1, round(h * 0.08))
    top_feather_end = max(top_full + 1, round(h * 0.11))
    out[:top_full] = target[:top_full]
    for y in range(top_full, min(h, top_feather_end)):
        alpha = 1.0 - (y - top_full) / max(1, top_feather_end - top_full)
        out[y] = out[y] * (1.0 - alpha) + target[y] * alpha

    bottom_feather_start = min(h - 1, round(h * 0.92))
    bottom_full = min(h, max(bottom_feather_start + 1, round(h * 0.95)))
    for y in range(bottom_feather_start, bottom_full):
        alpha = (y - bottom_feather_start) / max(1, bottom_full - bottom_feather_start)
        out[y] = out[y] * (1.0 - alpha) + target[y] * alpha
    out[bottom_full:] = target[bottom_full:]

    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGB")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def normalize_packshot(
    master: Path, profile: PackshotProfile | str | None = None
) -> tuple[Path, bool]:
    """Normalize `master` in place onto the profile, returning (path, applied).

    The pre-normalization render is preserved as `<stem>.raw.png`. On any
    rejection or error the master is left exactly as it was and applied=False
    comes back — normalization is an enhancement, never a reason for a render
    to fail.
    """
    profile = profile if isinstance(profile, PackshotProfile) else resolve_profile(profile)
    try:
        with Image.open(master) as im:
            im.load()
            src = im.convert("RGB")
            png_text = dict(getattr(im, "text", {}) or {})

        if profile.calibrate_only:
            out = _calibrate_field(src, profile)
        else:
            arr = np.asarray(src).astype(np.float32)
            matted = _product_alpha(arr, profile)
            if matted is None:
                return master, False
            alpha, solid, background = matted

            box = _bbox(solid)
            if box is None:
                logger.warning("Packshot matte rejected: empty product mask.")
                return master, False

            out = (
                _repaint_background(src, background, profile)
                if profile.repaint_only
                else _compose(src, alpha, box, profile)
            )

        # Preserve the nano_sofa_* identity chunks — history, EXIF derivation
        # and the variant chain all key off them.
        from PIL import PngImagePlugin
        info = PngImagePlugin.PngInfo()
        for k, v in png_text.items():
            info.add_text(k, v)

        raw = master.with_suffix(RAW_SUFFIX)
        if not raw.exists():
            shutil.copy2(master, raw)
        out.save(master, format="PNG", pnginfo=info)
        logger.info("Packshot normalized onto profile %r (bg=%s)", profile.name, profile.background)
        return master, True
    except Exception as exc:  # never let normalization break a render
        logger.warning("Packshot normalization skipped: %s", exc)
        return master, False
