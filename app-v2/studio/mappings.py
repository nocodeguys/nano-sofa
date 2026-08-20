"""Mappings: React state → GenerationRequest.

UI-id → English prompt fragment tables. Pure data (plus two pure helpers) —
no intra-package imports, so any module may import from here freely.
"""

from __future__ import annotations

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

# Cyclorama profile — locked multi-sentence spec. The packshot SCENE block
# in generator.py emits this verbatim when env_mode == "packshot". The level
# of detail is intentional: the loose one-liner ("clean white studio
# cyclorama") used to allow the model to reinterpret the backdrop on every
# render, which is exactly the inconsistency the user reported. With a fixed
# RGB, an explicit no-horizon-line clause, and a specific contact-shadow
# description, every packshot lands on the same look.
_CYCLORAMA_PROFILES = {
    "cyclorama_warm": (
        "a seamless infinity-curve studio cyclorama in warm off-white, base "
        "tone RGB(244,240,229) hex #F4F0E5 (the catalog warm cream used by "
        "premium European furniture brands). The backdrop has no visible "
        "horizon line between floor and wall — the curve is completely "
        "seamless. CRITICAL LIGHTING DETAIL: the cyclorama is NOT flat. "
        "A large overhead soft-box creates a visible, soft top-down "
        "lighting wash on the backdrop — the upper portion of the curve "
        "is fractionally brighter (about RGB 250,247,238) than the base "
        "tone, and the brightness fades gently toward the floor and the "
        "edges. This subtle top-light gradient is what gives the cyclorama "
        "dimension; without it the backdrop looks dead. SHADOW SPEC: a "
        "small, soft, anchored contact shadow sits directly beneath the "
        "product. Shadow color is a warm mid-grey RGB(200,195,180) — not "
        "black. Shadow edges are heavily blurred (gaussian-soft, no harsh "
        "silhouette). The shadow has zero directional cast — it is an "
        "anchor shadow only, not a thrown shadow. The shadow fades to "
        "invisibility within roughly 25 centimeters of the product's "
        "contact line with the floor. The floor under the product has a "
        "very subtle darkening gradient at the contact line, fading to the "
        "full backdrop tone within 30 centimeters. Absolutely no props, "
        "no walls, no floor seams, no environment objects, no other "
        "furniture, no plants, no rugs, no signage"
    ),
    "cyclorama_neutral": (
        "a seamless infinity-curve studio cyclorama in clean neutral white, "
        "base tone RGB(250,250,250) hex #FAFAFA (pure photo-studio white, "
        "no warm or cool tint). Otherwise identical to the warm cyclorama "
        "profile: seamless floor-to-wall curve, no horizon line. CRITICAL "
        "LIGHTING DETAIL: a large overhead soft-box creates a visible, "
        "soft top-down lighting wash on the backdrop — the upper portion "
        "of the curve is fractionally brighter (about RGB 255,255,255) "
        "than the base tone, fading gently toward the floor and edges. "
        "The gradient is subtle but visible — the cyclorama is not flat. "
        "SHADOW SPEC: small soft anchored contact shadow in mid-grey "
        "RGB(210,210,210), heavily blurred edges, zero directional cast, "
        "fading to invisibility within 25 cm of the contact line. Subtle "
        "floor darkening at the contact line, fading within 30 cm. No "
        "props, no walls, no environment objects of any kind"
    ),
    "cyclorama_grey": (
        "a seamless infinity-curve studio cyclorama in neutral mid-grey, "
        "base tone RGB(220,220,220) hex #DCDCDC (packshot grey, slightly "
        "cooler than neutral white). Seamless floor-to-wall curve, no "
        "horizon line. CRITICAL LIGHTING DETAIL: visible soft top-down "
        "lighting wash — upper portion of the curve fractionally brighter "
        "(about RGB 235,235,235) than the base tone, fading toward floor "
        "and edges. The cyclorama is not flat. SHADOW SPEC: small soft "
        "anchored contact shadow in darker grey RGB(180,180,180), heavily "
        "blurred edges, zero directional cast, fading within 25 cm. "
        "Subtle floor darkening at the contact line. No props, no walls, "
        "no environment objects"
    ),
    "cyclorama_transparent": (
        "transparent background output (alpha PNG) — the product is isolated "
        "with no backdrop at all. Render only the product with a small soft "
        "warm-grey contact shadow beneath it (RGB 200,195,180, heavily "
        "blurred, no directional cast); everything else is fully transparent. "
        "No floor, no wall, no environment, no other objects"
    ),
    "cyclorama_paperwhite": (
        "a seamless, minimalist studio cyclorama in bright off-white — a "
        "lifted, airy version of the softlight setup. There is NO visible "
        "horizon line and NO floor-to-wall seam; the curve is a perfectly "
        "continuous infinity sweep. BACKDROP COLOR (locked, uniform): a "
        "very bright but still off-white tone at RGB(252,250,247) hex "
        "#FCFAF7. The faint warm tint is intentional — this is off-white, "
        "NOT stark pure white, NOT hospital white, NOT pure RGB(255,255,255). "
        "If the rendered backdrop reads as #FFFFFF pure white, the color is "
        "wrong; it must retain a barely-perceptible warm cream undertone. "
        "This exact tone must cover the ENTIRE backdrop and floor with "
        "ZERO luminance variation. The cyclorama is rendered as one "
        "perfectly flat color field — like a painted wall, not a "
        "photographed surface. CRITICAL ANTI-HOTSPOT RULE: no part of the "
        "backdrop or floor may be brighter than RGB(254,252,250) or darker "
        "than RGB(249,247,244). Forbidden artifacts — each of these is a "
        "defect: a circular bright glow anywhere on the backdrop, a soft "
        "halo behind or above the product, a visible patch where the key "
        "light hits the cyclorama, a brighter upper-left corner, a "
        "brighter upper-right corner, a brighter band along any edge, ANY "
        "luminance gradient or falloff or vignette of any kind on the "
        "backdrop, ANY specular sheen, ANY visible evidence of where the "
        "light source is positioned. Treat the backdrop as a flat painted "
        "surface that ignores the studio lighting setup entirely — the "
        "light source is OFF-FRAME and does NOT register on the wall. If "
        "a viewer can locate the key light from the backdrop alone, the "
        "render has failed. PRODUCT LIGHTING (separate from backdrop): "
        "soft, diffused, even high-key lighting from a slightly elevated "
        "frontal-left angle. Lifts the product to a bright airy exposure "
        "with gentle form-defining shading on the product surfaces only — "
        "never spilling onto the backdrop. SHADOW (extremely subtle, "
        "almost invisible): a single whisper-soft contact shadow anchors "
        "the product to the floor. Shadow color is a very pale warm grey "
        "RGB(242,238,232). Opacity is ONLY 4–7 percent at its densest "
        "core, never darker — this is a barely-perceptible ground hint, "
        "NOT a drop shadow. The shadow feathers gently toward the RIGHT "
        "side of the frame. Edges are heavily gaussian-blurred; shadow "
        "fades to fully invisible within 10–14 centimeters of the product. "
        "CRITICAL: if you can clearly see the shadow as a distinct dark "
        "shape, it is TOO STRONG — make it lighter. The shadow should "
        "read more as a subtle softening of the floor tone than as a "
        "defined area. No second shadow on the left, no rim shadow, no "
        "stray cast shadows. TEXTURE: the entire backdrop is completely "
        "smooth and matte — zero film grain, zero paper fibers, zero "
        "specular reflection, zero environmental detail, zero noise, zero "
        "imperfections. Ultra-minimalist clean studio aesthetic. Absolutely "
        "no props, no furniture, no plants, no architectural elements, no "
        "signage, no overlaid text"
    ),
    "cyclorama_softlight": (
        "a seamless, minimalist studio cyclorama in clean off-white. There is "
        "NO visible horizon line and NO floor-to-wall seam — the curve is a "
        "perfectly continuous infinity sweep. BACKDROP COLOR (locked, "
        "uniform): a soft warm off-white at RGB(250,248,246) hex #FAF8F6. "
        "This exact tone must cover the ENTIRE backdrop and floor with "
        "ZERO luminance variation. The cyclorama is rendered as one "
        "perfectly flat color field — like a painted wall, not a "
        "photographed surface. CRITICAL ANTI-HOTSPOT RULE: no part of the "
        "backdrop or floor may be brighter than RGB(252,250,248) or darker "
        "than RGB(247,245,243). Forbidden artifacts — each of these is a "
        "defect that ruins the image: a circular bright glow anywhere on "
        "the backdrop, a soft halo behind or above the product, a visible "
        "patch where the key light hits the cyclorama, a brighter upper-"
        "left corner, a brighter upper-right corner, a brighter band along "
        "any edge, ANY luminance gradient or falloff or vignette of any "
        "kind on the backdrop, ANY specular sheen, ANY visible evidence "
        "of where the light source is positioned. Treat the backdrop as a "
        "flat painted surface that ignores the studio lighting setup "
        "entirely — the light source is OFF-FRAME and does NOT register "
        "on the wall. If a viewer can locate the key light from looking "
        "at the backdrop alone, the render has failed. PRODUCT LIGHTING "
        "(separate from backdrop): the product itself is lit with soft, "
        "diffused, even high-key lighting from a slightly elevated "
        "frontal-left angle, producing gentle form-defining shading on "
        "the product surfaces only — never spilling onto the backdrop. "
        "SHADOW (extremely subtle, almost invisible): a single whisper-"
        "soft contact shadow anchors the product to the floor. Shadow "
        "color is a very pale warm grey RGB(238,234,228). Opacity is ONLY "
        "5–8 percent at its densest core, never darker — this is a "
        "barely-perceptible ground hint, NOT a drop shadow. The shadow "
        "feathers gently toward the RIGHT side of the frame. Edges are "
        "heavily gaussian-blurred; shadow fades to fully invisible within "
        "10–15 centimeters of the product. CRITICAL: if you can clearly "
        "see the shadow as a distinct dark shape, it is TOO STRONG — make "
        "it lighter. The shadow should read more as a subtle softening of "
        "the floor tone than as a defined area. No second shadow on the "
        "left, no rim shadow, no stray cast shadows, no dark patches "
        "anywhere on the floor. TEXTURE: the entire backdrop is completely "
        "smooth and matte — zero film grain, zero paper fibers, zero "
        "specular reflection, zero environmental detail, zero noise, zero "
        "imperfections. Ultra-minimalist clean studio aesthetic. Absolutely "
        "no props, no furniture, no plants, no architectural elements, no "
        "signage, no overlaid text"
    ),
    "cyclorama_architectural": (
        "a seamless architectural-studio backdrop in warm soft ivory, base "
        "tone RGB(247,243,234) hex #F7F3EA — a clean off-white that reads as "
        "warm and architectural, NOT a stark hospital or pure-photo white. "
        "There is NO visible horizon line and NO visible floor-to-wall seam; "
        "the surface behaves like a perfect floating cyclorama with the "
        "product appearing to rest on a continuous ivory plane. CRITICAL "
        "LIGHTING DETAIL: high-key, even studio lighting with a single large "
        "soft-box key light positioned at the TOP-LEFT of the frame. This "
        "produces a gentle directional wash: the floor area in front of and "
        "around the product is fractionally BRIGHTER (about RGB 252,249,242) "
        "than the upper portion of the backdrop, which softens by 4–6 RGB "
        "values toward the top edge. The gradient is subtle but visible — "
        "the lower third of the frame should clearly read as the brightest "
        "zone. The overall exposure is high-key (bright, airy, no deep "
        "midtones in the backdrop). SHADOW SPEC: a single soft diffused drop "
        "shadow anchors the product to the floor. The shadow is densest "
        "directly beneath the product's contact footprint (warm mid-grey "
        "RGB 215,208,196, roughly 30–40 percent opacity at its core), and "
        "feathers out smoothly toward the RIGHT side of the frame — the "
        "natural shadow direction for a top-left key light. The shadow's "
        "right edge fades gradually to invisibility within roughly 35–45 "
        "centimeters of the product, with heavily blurred, gaussian-soft "
        "edges throughout. No second shadow on the left side. TEXTURE: the "
        "entire backdrop is completely smooth and matte — zero film grain, "
        "zero specular reflections, zero environmental detail, zero texture "
        "noise, no paper fibers, no wall imperfections. Absolutely no props, "
        "no furniture, no plants, no architectural elements, no signage"
    ),
}

# Environment id (from data.jsx ENVIRONMENTS) → (mode, scene description).
# Mode drives the two branches of the SCENE block in generator.py:
#   "packshot"  → product on a clean backdrop, no room context.
#   "lifestyle" → product staged inside a real interior, environment first-class.
_ENV_TO_SCENE = {
    # Cyclorama presets — locked profiles that always look the same.
    "cyclorama_warm":        ("packshot", _CYCLORAMA_PROFILES["cyclorama_warm"]),
    "cyclorama_neutral":     ("packshot", _CYCLORAMA_PROFILES["cyclorama_neutral"]),
    "cyclorama_grey":        ("packshot", _CYCLORAMA_PROFILES["cyclorama_grey"]),
    "cyclorama_transparent": ("packshot", _CYCLORAMA_PROFILES["cyclorama_transparent"]),
    "cyclorama_architectural": ("packshot", _CYCLORAMA_PROFILES["cyclorama_architectural"]),
    "cyclorama_softlight":     ("packshot", _CYCLORAMA_PROFILES["cyclorama_softlight"]),
    "cyclorama_paperwhite":    ("packshot", _CYCLORAMA_PROFILES["cyclorama_paperwhite"]),
    # Legacy aliases — point at the new locked profiles so existing wizard
    # users automatically inherit the consistency upgrade.
    "studio_white":          ("packshot", _CYCLORAMA_PROFILES["cyclorama_warm"]),
    "studio_grey":           ("packshot", _CYCLORAMA_PROFILES["cyclorama_grey"]),
    "transparent":           ("packshot", _CYCLORAMA_PROFILES["cyclorama_transparent"]),
    # Lifestyle envs — unchanged narrative descriptions.
    "scandi":        ("lifestyle", "a scandinavian living room with light oak floors, white walls, and indoor plants"),
    "loft":          ("lifestyle", "an industrial loft with exposed brick walls, polished concrete floors, and dark metal accents"),
    "japandi":       ("lifestyle", "a japandi interior with a warm minimalist palette, natural wood, and soft diffuse light"),
    "boho":          ("lifestyle", "a bohemian living room with rattan furniture, woven textiles, and warm earthy tones"),
    "dark_moody":    ("lifestyle", "a moody dark interior with deep painted walls and warm pendant lamp lighting"),
    "garden":        ("lifestyle", "an outdoor terrace / garden setting with greenery and natural daylight"),
    "showroom":      ("lifestyle", "a brand showroom with subtle product staging and a neutral palette"),
    "custom":        ("lifestyle", "the custom interior shown in the user's uploaded background reference image"),
}

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
    "linen_white":   "crisp white pure-linen sheets and a matching white linen duvet, gentle natural creases, soft matte texture",
    "linen_natural": "natural undyed flax linen sheets and duvet in warm ecru / oatmeal tone, visible weave, soft wrinkles",
    "linen_grey":    "stone-grey washed linen sheets and duvet, gently rumpled, slightly cool undertone",
    "linen_sage":    "muted sage-green washed linen sheets and duvet, soft and matte",
    "cotton_white":  "smooth white percale cotton sheets and duvet, crisp and lightly pressed, hotel-look finish",
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
    seed: str = "",
    n_refs: int = 0,
) -> str:
    """
    Compose the full editorial prompt: the user's brief leads, picker
    fragments follow as art-direction constraints. Every picker is optional —
    empty ids are simply skipped, so the minimal prompt is TASK + BRIEF +
    OUTPUT STYLE.
    """
    lines: list[str] = [
        "TASK: Create a brand-new editorial photograph from scratch based on "
        "the brief below. There is no base product to preserve — full "
        "creative freedom within the art direction."
    ]
    if n_refs:
        lines.append(
            f"Use the {n_refs} attached image(s) as loose mood and styling "
            "inspiration only — do not copy them literally."
        )
    lines.append("")
    lines.append(f"BRIEF: {text.strip()}")
    lines.append("")

    if style in _EDITORIAL_STYLES:
        lines.append(f"ART DIRECTION: {_EDITORIAL_STYLES[style]}.")
    if env and env in _ENV_TO_SCENE and env != "custom":
        lines.append(f"SETTING: {_ENV_TO_SCENE[env][1]}.")
    if tod in _TOD_TO_PROMPT:
        lines.append(f"LIGHT: {_TOD_TO_PROMPT[tod]}.")
    cam_bits = []
    if lens in _LENS_TO_PROMPT:
        cam_bits.append(_LENS_TO_PROMPT[lens]["descriptor"])
    if height in _HEIGHT_TO_PHRASE:
        cam_bits.append(_HEIGHT_TO_PHRASE[height])
    if cam_bits:
        lines.append("CAMERA: " + "; ".join(cam_bits) + ".")
    if color_en:
        lines.append(
            f"COLOR DIRECTION: build the palette around {color_en} as the "
            "dominant tone, supported by harmonious neutrals."
        )
    if mat_noun_en:
        tex_hint = mat_texture_en.split(".")[0].strip()
        lines.append(
            f"TEXTILE DIRECTION: featured fabrics read as {mat_noun_en}"
            + (f" — {tex_hint}." if tex_hint else ".")
        )
    if seed.strip():
        lines.append(f"seed hint: {seed.strip()}")

    lines.append("")
    lines.append(
        "OUTPUT STYLE: professional editorial furniture-brand photography, "
        "photorealistic, coherent high-end art direction, natural color grading."
    )
    lines.append(
        "NEGATIVE (must not appear in output): any rendered text, typography, "
        "logos, watermarks or UI elements — leave clean negative space where "
        "a masthead or headline would be placed."
    )
    return "\n".join(lines)
