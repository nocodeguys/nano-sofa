"""Mappings: React state → GenerationRequest.

UI-id → English prompt fragment tables. Pure data (plus two pure helpers) —
no intra-package imports, so any module may import from here freely.
"""

from __future__ import annotations

from app.core.prompt import compile_prompt, freeform_spec
from studio.catalog import (
    BACKDROPS, CUSTOM_BACKGROUND_ID, CUSTOM_BACKGROUND_PROMPT, DEFAULT_BACKDROP_ID,
    SCENES, resolve_background,
)

_SOFA_CONFIG = {
    "1": "armchair",
    "2": "2-seater",
    "3": "3-seater",
    "4": "4-seater",
    "L": "L-shaped sectional",
    "U": "U-shaped sectional",
}
_BED_CONFIG = {"90": "90x200 single", "120": "120x200 french", "140": "140x200 double",
               "160": "160x200 queen", "180": "180x200 king"}

_LEG_TO_ID = {
    "keep": None,
    "wood": "tapered-wood",
    "metal": "hairpin-metal",
    "block": "block-wood",
    "hidden": "plinth-hidden",
    "swivel": "swivel-base",
}

# Backdrop prompt paragraphs live in catalog.json (`backdrops[].prompt_en`);
# this view keeps the old name for callers. Keyed by canonical id AND by
# every alias (old env ids) so stale presets keep resolving.
def _backdrop_prompts() -> dict[str, str]:
    out: dict[str, str] = {}
    for b in BACKDROPS.values():
        out[b["id"]] = b["prompt_en"]
        for alias in b.get("aliases", []) or []:
            out[alias] = b["prompt_en"]
    return out


_CYCLORAMA_PROFILES = _backdrop_prompts()

# ---------------------------------------------------------------------------
# Catalog profile — the "one shoot" contract.
#
# Two products photographed with identical wizard settings still land on
# different subject scales, because every framing string in the table above is
# qualitative: "breathing room above and below" means one thing for a low
# platform bed and another for a continental bed with a tall headboard. Across
# a product grid that reads as eight separate photo sessions.
#
# Catalog mode fixes both halves of the problem:
#   * _CATALOG_LOCKS pins every look-defining setting to one value, so no two
#     products can be shot on different backdrops or lenses by accident. Yaw is
#     deliberately NOT locked — which side a product is turned toward is a real
#     per-product decision, unlike the backdrop.
#   * _CATALOG_FRAMING_CONTRACT states subject scale, centring and floor-contact
#     height as percentages of the frame, so the model has nothing left to
#     interpret.
#
# The percentages match studio/normalize.py's PackshotProfile. That is the point:
# the render should land close enough that the deterministic normalization pass
# only has to nudge it, rather than upscale a small product and soften it.
# ---------------------------------------------------------------------------
_CATALOG_LOCKS = {
    "shot":   "hero",
    "height": "eye",
    "lens":   "85mm_product",
    "dof":    "deep",               # f/8 — no background separation on a cyclorama
    "tod":    "noon_neutral",
    "shadow": "soft_diffuse",
}

# Locked backdrops (catalog treatment) come from catalog.json: a backdrop
# with a `locks` block pins lens / aperture / light / camera height so every
# product of a range is shot in the same studio. `_CATALOG_LOCKS` is the
# fallback set when an entry omits a key.
_CATALOG_PROFILE_DEFAULT = DEFAULT_BACKDROP_ID


def _catalog_profile_locks(profile: str) -> dict:
    """Locks for a backdrop id (or alias); unknown ids → the default backdrop."""
    kind, entry = resolve_background(profile)
    if kind != "backdrop" or not entry.get("locks"):
        entry = BACKDROPS[DEFAULT_BACKDROP_ID]
    return {**_CATALOG_LOCKS, **(entry.get("locks") or {}), "env": entry["id"]}

# Shot type → numeric framing clause. Detail and close-up shots are absent on
# purpose: a macro crop has no "subject scale within the frame" to lock, and
# normalize.py refuses to touch those renders for the same reason.
_CATALOG_FRAMING_CONTRACT = {
    "hero": (
        "CATALOG FRAMING CONTRACT (hard requirement, overrides any looser "
        "framing language above): the product's widest visible extent spans "
        "78-84 percent of the frame width. The product's total height occupies "
        "no more than 70 percent of the frame height. The product is centred "
        "horizontally with equal empty margins left and right. The product's "
        "lowest point of contact with the floor sits at 86-90 percent of the "
        "frame height, measured downward from the top edge of the frame. The "
        "backdrop fills every remaining margin. Do not crop the product at any "
        "frame edge, do not zoom in tighter than this, and do not pull back "
        "further than this."
    ),
    "wide": (
        "CATALOG FRAMING CONTRACT (hard requirement, overrides any looser "
        "framing language above): the product's widest visible extent spans "
        "50-56 percent of the frame width, centred horizontally with equal "
        "margins. The product's lowest point of contact with the floor sits at "
        "78-82 percent of the frame height, measured downward from the top "
        "edge. Do not crop the product at any frame edge."
    ),
    "three_quarter": (
        "CATALOG FRAMING CONTRACT (hard requirement, overrides any looser "
        "framing language above): the product's widest visible extent spans "
        "88-94 percent of the frame width, centred horizontally. The product's "
        "lowest point of contact with the floor sits at 88-92 percent of the "
        "frame height, measured downward from the top edge. Do not crop the "
        "product at any frame edge."
    ),
}


def _catalog_framing_contract(shot_id: str) -> str:
    """Numeric framing clause for a shot type, or "" when it doesn't apply."""
    return _CATALOG_FRAMING_CONTRACT.get(shot_id, "")


# Environment id (from data.jsx ENVIRONMENTS) → (mode, scene description).
# Mode drives the two branches of the SCENE block in generator.py:
#   "packshot"  → product on a clean backdrop, no room context.
#   "lifestyle" → product staged inside a real interior, environment first-class.
def _env_to_scene() -> dict[str, tuple[str, str]]:
    """env id → (mode, prompt): every backdrop (packshot) under its id and
    aliases, every scene (lifestyle), and the custom upload."""
    out: dict[str, tuple[str, str]] = {}
    for b in BACKDROPS.values():
        out[b["id"]] = ("packshot", b["prompt_en"])
        for alias in b.get("aliases", []) or []:
            out[alias] = ("packshot", b["prompt_en"])
    for sc in SCENES.values():
        out[sc["id"]] = ("lifestyle", sc["prompt_en"])
    out[CUSTOM_BACKGROUND_ID] = ("lifestyle", CUSTOM_BACKGROUND_PROMPT)
    return out


_ENV_TO_SCENE = _env_to_scene()

# Canonical key is the English `id` from data.jsx (LENSES / TIMES_OF_DAY /
# SHADOWS). Polish display strings are accepted too for backward compatibility
# with browser caches that still hold the pre-2026-05 UI — see the alias
# tables below. Once we trust everyone is on the new build these aliases can
# be deleted.

# English id → English narrative for time-of-day / lighting quality.
# Feeds GenerationRequest.tod_description, which lands inside the SCENE block.
_TOD_TO_PROMPT = {
    "morning_cool": "early morning cool soft light, approximately 4500 K, low-angle long shadows from one side",
    "noon_neutral": "midday neutral daylight, approximately 5500 K, overhead light with short even shadows",
    "golden_hour":  "golden-hour warm directional light, approximately 3000 K, long warm shadows, golden cast across the scene",
    "evening_lamp": "evening warm artificial lamp lighting, approximately 2800 K, low ambient light with pools of warm illumination",
}
_TOD_LEGACY_ALIAS = {
    "poranek — chłodne, miękkie":  "morning_cool",
    "południe — neutralne":         "noon_neutral",
    "złota godzina — ciepłe":       "golden_hour",
    "wieczór — lampy":              "evening_lamp",
}

# English id → focal length + intent descriptor.
# Captures lens *intent* (catalog / product / wide) that focal length alone discards.
_LENS_TO_PROMPT = {
    "35mm_wide":    {"focal_mm": 35, "descriptor": "35 mm wide-angle, includes generous environment context, slight perspective exaggeration"},
    "50mm_natural": {"focal_mm": 50, "descriptor": "50 mm natural perspective, matches the human eye, standard catalog framing"},
    "85mm_product": {"focal_mm": 85, "descriptor": "85 mm short telephoto, mild background compression, flattering product photography standard"},
    "100mm_macro":  {"focal_mm": 100, "descriptor": "100 mm macro lens, extreme close-focus capability, razor-thin depth of field at minimum focus distance, flat field rendering of fabric texture detail"},
}
_LENS_LEGACY_ALIAS = {
    "35 mm — szeroki kontekst": "35mm_wide",
    "50 mm — naturalna":         "50mm_natural",
    "85 mm — produktowa":        "85mm_product",
    "100 mm makro":              "100mm_macro",
}
_LENS_DEFAULT = {"focal_mm": 50, "descriptor": "50 mm natural perspective, standard catalog framing"}

# ---------------------------------------------------------------------------
# Shot type → framing template. The user picks one of six framing intents
# in the Camera step; the server emits the matching framing string into
# GenerationRequest.framing.  Detail variants ALSO flip GenerationRequest
# .shot_type which causes generator.py to suppress the yaw line in the
# CAMERA block and emit an OOF-background SCENE block — without those two
# changes the cyclorama profile text overrides the detail crop instruction
# (the bug the user reported as "can't generate detail photo").
#
# The `{region}` placeholder is filled in by `_compose_detail_framing()`
# from the chosen detail_region (when shot_type is a detail variant).
# ---------------------------------------------------------------------------
_SHOT_TYPE_TO_FRAMING = {
    "wide":          "wide establishing shot, product occupies the central third of the frame, generous environment context above and around the product",
    "hero":          "full product visible with breathing room above and below, classic catalog hero framing centered in the frame",
    "three_quarter": "product fills roughly three quarters of the frame, slight crop at frame edges is allowed, no environment context visible",
    "cropped":       "compositional crop along thirds, product fills most of the frame, intentional cuts at the frame edges, no environment context visible",
    "close_up":      "close-up shot of {region}; only that section of the product is visible in the frame; the rest of the product is intentionally cropped at the frame edge; product anatomy is still recognizable but the framing is tight on the chosen region",
    "detail_fabric": "extreme macro close-up of {region}; the frame is filled by fabric texture only; no product silhouette, no product edges, no full-product shapes anywhere in the frame",
    "detail_corner": "tight macro crop on {region}; only that single region of the product is visible; the rest of the product is intentionally cropped out by the frame edge",
}

# Detail / close-up region id → English phrase. Substituted into the framing template.
# Region IDs are namespaced by product/region kind to avoid collisions across
# the three region pickers (fabric macro / mechanical detail / section close-up).
_DETAIL_REGION_TO_PHRASE = {
    # Fabric-macro regions (extreme close, no product silhouette)
    "weave":   "the upholstery fabric weave pattern, individual warp and weft threads visible",
    "nap":     "the upholstery fabric pile / nap (velvet or boucle short-pile texture)",
    "threads": "the individual fibers and thread structure of the upholstery, linen-style weave",
    "boucle":  "the looped boucle yarn structure of the upholstery, individual loops visible",
    # Small mechanical-detail regions (stitching, joinery)
    "arm_back_corner": "the corner where the armrest meets the backrest of the product",
    "cushion_edge":    "the edge of a seat cushion against the frame, showing piping and seam",
    "panel_seam":      "the seam where two upholstery panels are joined, stitching visible",
    "leg_attachment":  "the point where a leg meets the underside of the frame, joinery visible",
    # Bed section close-ups
    "bed_headboard":   "the front of the headboard and the top half of the bed, the lower half of the bed cropped at the frame edge",
    "bed_side":        "the side profile of the bed, showing the side rail, the foot end, and the lower portion of the headboard",
    "bed_foot":        "the foot end of the bed viewed end-on, the headboard not visible in the frame",
    "bed_back":        "the back of the headboard, viewed from behind the bed, the mattress only partially visible",
    "bed_corner_head": "the headboard-end corner of the bed in three-quarter view, showing the corner of the headboard, the head of the side rail, and a small portion of the mattress",
    "bed_corner_foot": "the foot-end corner of the bed in three-quarter view, showing the corner where the side rail meets the foot of the bed",
    # Sofa section close-ups
    "sofa_armrest":  "one armrest of the sofa with the adjacent seat cushion, the rest of the sofa cropped at the frame edge",
    "sofa_backrest": "the top half of the sofa backrest, the seat cushions only partially visible at the bottom of the frame",
    "sofa_seat":     "the seat cushions and the front edge of the sofa, the backrest and armrests partially cropped",
    "sofa_corner":   "one full-height corner of the sofa, showing the armrest, the backrest, and the seat at that corner",
    "sofa_side":     "the side profile of the sofa, showing one armrest end-on and the side of the seat and backrest",
    "sofa_back":     "the back of the sofa, rear elevation view, no front-facing upholstery visible",
}
_DETAIL_REGION_DEFAULT_FABRIC = "weave"
_DETAIL_REGION_DEFAULT_CORNER = "arm_back_corner"
_CLOSE_REGION_DEFAULT_BED  = "bed_corner_head"
_CLOSE_REGION_DEFAULT_SOFA = "sofa_corner"

# Camera yaw → (camera_angle_label, degrees-from-left).
# Replaces the old _CAMERA_TO_ANGLE table that bundled shot type and yaw
# together. With shot type now independent, yaw is a pure orientation pick.
_YAW_TO_ANGLE = {
    "front":      ("front-on",        0),
    "34_left":    ("front-34-left",  35),
    "34_right":   ("front-34-right", 35),
    "side_left":  ("side-left",      90),
    "side_right": ("side-right",     90),
    "back":       ("back",          180),
}

# Camera height → descriptive phrase woven into the CAMERA line.
_HEIGHT_TO_PHRASE = {
    "low":      "low camera height, roughly knee-level",
    "seated":   "seated camera height, roughly chair-seat-level",
    "eye":      "eye-level camera height, standing adult viewpoint",
    "standing": "raised camera height, slightly above standing eye-level",
    "overhead": "overhead camera height, looking down at approximately 45 degrees",
}

# Depth of field → aperture. Pairs with lens (focal length); together they
# determine how blurred the background renders.
_DOF_TO_APERTURE = {
    "deep":          "f/8.0",
    "standard":      "f/4.5",
    "shallow":       "f/2.0",
    "macro_shallow": "f/2.8",
}

# Legacy `cam` preset → (shot_type, yaw, height) triple. Used when the
# request only carries the old single `cam` field (older browser cache or
# the quick-preset buttons in the new UI). Lets us deprecate `cam` without
# breaking existing form posts.
_CAM_PRESET_TO_STRUCTURED = {
    "studio": ("hero",          "34_left",  "eye"),
    "lounge": ("hero",          "34_right", "eye"),
    "loft":   ("hero",          "34_left",  "eye"),
    "detail": ("detail_fabric", "front",    "eye"),
    "eye":    ("hero",          "front",    "eye"),
    "top":    ("hero",          "front",    "overhead"),
}

# English id → (clock-position direction, full English description).
# `direction` keeps backward compat with the existing shadow_direction field;
# `desc` is the narrative sentence that flows into the SCENE block.
_SHADOW_TO_PROMPT = {
    "soft_diffuse":  {"direction": "soft diffuse",
                      "desc": "soft diffuse shadow beneath the product, no strong directional cast, soft-box lighting quality"},
    "directional_4": {"direction": "4 o-clock",
                      "desc": "directional shadow falling toward 4 o-clock, suggesting window light from the upper left"},
    "hard_studio_5": {"direction": "5 o-clock",
                      "desc": "hard-edged shadow falling toward 5 o-clock, suggesting a studio strobe from the upper right"},
}
_SHADOW_LEGACY_ALIAS = {
    "miękkie rozproszone": "soft_diffuse",
    "kierunkowe — okno":   "directional_4",
    "twarde — studio":     "hard_studio_5",
}
_SHADOW_DEFAULT = {"direction": "soft diffuse",
                   "desc": "soft diffuse shadow beneath the product, no strong directional cast"}

# ---------------------------------------------------------------------------
# Bed styling — section 10 in the wizard. Each preset id maps to an English
# clause that becomes part of the BEDDING block emitted by the generator
# (see generator._build_prompt_text). When the user picks "custom" for
# bedding, the free-text field replaces the preset; for everything else
# we compose the clauses by concatenation. Empty for sofas.
# ---------------------------------------------------------------------------
_BEDDING_TO_PROMPT = {
    "none":          "no bedding at all — the bare mattress is visible, no sheets, no duvet, no pillows",
    "linen_white":   "crisp white pure-linen sheets and a matching white linen duvet, matte rather than luminous, gentle natural creases with clearly visible tonal modelling and weave in every highlight",
    "linen_natural": "natural undyed flax linen sheets and duvet in warm ecru / oatmeal tone, visible weave, soft wrinkles",
    "linen_grey":    "stone-grey washed linen sheets and duvet, gently rumpled, slightly cool undertone",
    "linen_sage":    "muted sage-green washed linen sheets and duvet, soft and matte",
    "cotton_white":  "smooth white percale cotton sheets and duvet, crisp and lightly pressed, hotel-look finish, with preserved seam relief and soft upper-mid-grey fold definition rather than clipped pure-white planes",
    "jersey_warm":   "soft cream cotton-jersey sheets and a matching jersey duvet, cozy and relaxed drape",
}
_THROW_TO_PROMPT = {
    "linen_foot":  "a light-weight linen throw folded neatly at the foot of the bed",
    "knit_chunky": "a chunky hand-knit wool throw casually draped across the lower third of the bed",
    "wool_plaid":  "a folded wool plaid blanket placed across the foot of the bed",
    "boucle":      "a soft cream bouclé throw lightly tossed across one corner of the bed",
    "quilt":       "a vintage-style quilted bedspread folded along the foot, lightly textured",
}
_TIDY_TO_PROMPT = {
    "unmade":   "the bed is unmade — sheets pulled aside, duvet partly thrown off, a clearly slept-in look. Casual and very lived-in, but still photogenic and not chaotic",
    "lived_in": "the bedding is naturally rumpled with soft organic creases and gentle wrinkles — a lived-in but pleasant look, not staged-stiff and not messy",
    "neat":     "the bedding is smoothed and tidy with only subtle natural wrinkles, the duvet centered and even, pillows neatly arranged. Calm and orderly",
    "hotel":    "the bedding is crisp and hotel-perfect — taut sheets, perfectly squared duvet corners, pillows precisely stacked and fluffed, zero wrinkles, magazine-grade styling",
    "five_star": (
        "the bedding is rendered to ultra-luxury five-star hotel suite standard: "
        "ABSOLUTELY zero folds, zero creases, zero wrinkles, zero rumples anywhere "
        "on the sheets, duvet, or pillowcases. Every surface is ironed glass-smooth "
        "and pulled taut to the millimeter. Duvet corners are knife-sharp 90-degree "
        "right angles, perfectly squared and aligned to the mattress edges. The "
        "duvet itself lies flat and evenly tensioned across the entire bed with no "
        "air bubbles, no puckering, and no soft sag. Pillows are flawlessly fluffed, "
        "identical in height and shape, precisely stacked or aligned with "
        "mathematical symmetry. Sheet edges are crisp and perfectly parallel. "
        "Top-tier luxury presentation, like a Mandarin Oriental or Four Seasons "
        "master suite immediately after housekeeping turn-down. ANY visible fold, "
        "wrinkle, or asymmetry on the bedding is a defect that ruins the render"
    ),
}
_DENSITY_TO_PROMPT = {
    "minimal":  "an extremely minimal scene — only the bed and its bedding are visible, absolutely no decorative props, no books, no trays, no plants, no extra objects in the frame",
    "balanced": "a balanced scene with the bedding and at most one or two small tasteful styling items if listed below; otherwise the frame stays clean",
    "rich":     "a fully styled editorial-look scene with multiple tasteful styling items adding warmth and narrative — but never cluttered or busy",
}
_ACCENT_TO_PROMPT = {
    "extra_pillows": "an extra pair of decorative pillows neatly arranged against the headboard",
    "book":          "a single hardback book resting on top of the duvet, casually placed",
    "tray":          "a small wooden breakfast tray with a coffee cup placed on the bed",
    "robe":          "a soft linen robe casually laid across the corner of the bed",
    "plant":         "a small potted plant visible on a nightstand or just beside the bed",
    "candle":        "a single lit candle in a simple ceramic holder placed near the bed",
}


def _compose_bedding_description(
    *,
    bedding: str,
    bedding_custom: str,
    throw: str,
    tidy: str,
    density: str,
    accents_csv: str,
    bed_note: str,
) -> str:
    """
    Translate the wizard's section-10 selections into one narrative paragraph
    that the generator emits as the BEDDING & STYLING block. Returns "" when
    the user left every field at empty/default — that suppresses the block
    entirely so the prompt stays clean for sofas and bed-no-styling cases.
    """
    parts: list[str] = []

    # Bedding textile — preset OR custom free text.
    bedding_id = (bedding or "").strip().lower()
    custom_text = (bedding_custom or "").strip()
    if bedding_id == "custom" and custom_text:
        parts.append(custom_text)
    elif bedding_id in _BEDDING_TO_PROMPT:
        parts.append(_BEDDING_TO_PROMPT[bedding_id])

    # Throw / extra blanket.
    throw_id = (throw or "").strip().lower()
    if throw_id in _THROW_TO_PROMPT:
        parts.append(_THROW_TO_PROMPT[throw_id])

    # Tidiness / arrangement.
    tidy_id = (tidy or "").strip().lower()
    if tidy_id in _TIDY_TO_PROMPT:
        parts.append(_TIDY_TO_PROMPT[tidy_id])

    # Density / how busy the frame is.
    density_id = (density or "").strip().lower()
    if density_id in _DENSITY_TO_PROMPT:
        parts.append(_DENSITY_TO_PROMPT[density_id])

    # Optional decorative accents — silently dropped when density==minimal so
    # the prompt stays internally consistent (the UI also tells the user this).
    if density_id != "minimal":
        accent_ids = [a.strip() for a in (accents_csv or "").split(",") if a.strip()]
        accent_clauses = [_ACCENT_TO_PROMPT[a] for a in accent_ids if a in _ACCENT_TO_PROMPT]
        if accent_clauses:
            parts.append("Additional styling items in the frame: " + "; ".join(accent_clauses))

    # User's free-text override — appended last, highest authority for nuance.
    note = (bed_note or "").strip()
    if note:
        parts.append(f"Special styling note from the user: {note}")

    return ". ".join(parts).strip()


def _resolve_id(value: str, aliases: dict) -> str:
    """Map a possibly-legacy Polish UI string to its English id; pass through ids unchanged."""
    if not value:
        return value
    return aliases.get(value, value)


# ---------------------------------------------------------------------------
# Editorial (freeform) mode — /api/generate-free
# ---------------------------------------------------------------------------
# Style id → English art-direction fragment. Polish labels live in
# frontend/src/data.jsx EDITORIAL_STYLES, keyed by the same ids (the same
# pattern as ENVIRONMENTS / TIMES_OF_DAY).
_EDITORIAL_STYLES = {
    "magazine_cover": (
        "premium interior-magazine cover composition: one strong focal "
        "subject, bold clean negative space reserved at the top for a "
        "masthead and along one edge for cover lines, refined styling, "
        "high-end editorial lighting, subtle film-like grade"
    ),
    "web_hero": (
        "wide website hero-banner composition: calm horizontal flow, "
        "generous clean negative space on one side for a headline overlay, "
        "minimal styling, soft depth falloff"
    ),
    "editorial_spread": (
        "interior-magazine editorial spread: styled, lived-in scene with "
        "layered textiles and props, natural imperfections, storytelling "
        "composition in the manner of a premium architecture magazine feature"
    ),
    "campaign": (
        "seasonal brand-campaign key visual: evocative art-directed styling "
        "with seasonal accents, cohesive palette, cinematic light with "
        "gentle atmosphere"
    ),
    "art_minimal": (
        "minimal art-poster aesthetic: sculptural composition, bold geometry "
        "of light and shadow, generous abstract negative space, "
        "gallery-poster feel"
    ),
}


# People-in-frame options for the editorial page. Default "" = explicitly no
# people (goes into the NEGATIVE block — leaving it unstated makes the model
# add or omit figures at random between renders).
_PEOPLE_TO_PROMPT = {
    "silhouette": (
        "One anonymous human figure appears as a soft, out-of-focus "
        "silhouette in the background, adding scale and life to the scene; "
        "face not visible, no eye contact with the camera."
    ),
    "lifestyle": (
        "A person interacts naturally with the scene (resting, reading, "
        "stretching) in candid lifestyle-editorial style; relaxed unposed "
        "body language, soft natural styling, face softly lit, never looking "
        "into the camera."
    ),
    "hands": (
        "Only a human hand or forearm enters the frame (smoothing bedding, "
        "holding a mug) — intimate editorial detail-shot style; no face, no "
        "full figure."
    ),
}


def _build_freeform_prompt(
    *,
    text: str,
    style: str = "",
    env: str = "",
    tod: str = "",
    lens: str = "",
    height: str = "",
    color_en: str = "",
    mat_noun_en: str = "",
    mat_texture_en: str = "",
    mat_avoid_en: list[str] | None = None,
    people: str = "",
    seed: str = "",
    slots: dict[str, int] | None = None,
    color_hex: str = "",
) -> str:
    """
    Compose the full editorial prompt: picker ids are resolved to English
    fragments here (the tables live in this module), the wording and order
    live in app/core/prompt. Every picker is optional — empty ids are simply
    skipped, so the minimal prompt is TASK + BRIEF + OUTPUT STYLE.

    `slots` maps reference roles to the 1-based positions that are ACTUALLY
    attached (generator.plan_freeform_reference_slots after the engine's
    cap), so the prompt never describes an image the model did not receive.
    """
    spec = freeform_spec(
        text=text,
        art_direction=_EDITORIAL_STYLES.get(style, "") if style in _EDITORIAL_STYLES else "",
        setting_text=_ENV_TO_SCENE[env][1] if (env and env in _ENV_TO_SCENE and env != "custom") else "",
        light_text=_TOD_TO_PROMPT.get(tod, "") if tod in _TOD_TO_PROMPT else "",
        lens_descriptor=_LENS_TO_PROMPT[lens]["descriptor"] if lens in _LENS_TO_PROMPT else "",
        height_phrase=_HEIGHT_TO_PHRASE.get(height, "") if height in _HEIGHT_TO_PHRASE else "",
        color_en=color_en,
        mat_noun_en=mat_noun_en,
        mat_texture_en=mat_texture_en,
        mat_avoid_en=mat_avoid_en,
        people_text=_PEOPLE_TO_PROMPT[people] if people in _PEOPLE_TO_PROMPT else "",
        seed=seed,
        slots=slots,
        color_hex=color_hex,
    )
    return compile_prompt(spec)
