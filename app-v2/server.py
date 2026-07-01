"""
server.py — FastAPI backend for Nano Sofa Studio v2.

Serves the static React/HTML/CSS prototype from ./static and exposes:
  GET  /                   → Nano Sofa Studio v2.html (current design)
  GET  /v1                 → Nano Sofa Studio.html   (earlier design, static)
  GET  /healthz            → liveness + capability report (no API call)
  GET  /api/config         → model enum + per-model constraints
  POST /api/generate       → run a single generation
  GET  /api/outputs/<file> → serve a generated image

Wraps app/core/generator.py from the parent project (shared with v1).

Environment variables:
  PORT          listen port (default 7861)
  HOST          listen host (default 0.0.0.0)
  OUTPUTS_DIR   where generated images and uploads live (default <repo>/outputs)
                Mount this as a volume in Docker to persist renders.

Run with:
    cd <repo-root> && python app-v2/server.py
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sys
import uuid
from dataclasses import replace as dataclass_replace
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

# Make the parent project importable so we reuse app.core.generator
_THIS = Path(__file__).resolve().parent
_REPO_ROOT = _THIS.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.core.generator import GenerationRequest, classify_exception, generate  # noqa: E402
from app.core.cost_tracker import (  # noqa: E402
    output_path_for_generation,
    recent_generations,
)
from app.core.schema_loader import schema  # noqa: E402
from app.core.video_generator import (  # noqa: E402
    VideoRequest,
    generate_video,
    list_video_models,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nano-sofa-v2")

# ---------------------------------------------------------------------------
# Mappings: React state → GenerationRequest
# ---------------------------------------------------------------------------

# Colour id (from data.jsx COLORS) → English term the prompt uses. These are the
# TreeTale fabric-matrix colour GROUPS; each carries its representative hex so
# the model can anchor the exact shade. Keys must match data.jsx COLORS ids.
_COLOR_PL_TO_EN = {
    "cream":      "soft creamy off-white ivory, like natural unbleached cotton (hex #E7E0D6)",
    "sand":       "light sandy beige with warm champagne undertones (hex #D9D4CD)",
    "greige":     "neutral greige grey-beige, like light natural stone (hex #C3BEB6)",
    "cappuccino": "warm cappuccino latte beige (hex #B4A799)",
    "taupe":      "medium taupe blending grey and brown (hex #938A83)",
    "caramel":    "warm caramel honey-walnut brown (hex #9F693D)",
    "choc":       "deep dark chocolate brown / espresso (hex #4E3E2F)",
    "ash":        "light cool ash grey / silver (hex #BCBCBC)",
    "steelgrey":  "solid medium steel grey / stone (hex #908F8B)",
    "graphite":   "dark moody graphite / anthracite grey (hex #656F70)",
    "olive":      "muted earthy olive / sage green (hex #6A7763)",
    "forest":     "deep rich forest / bottle green (hex #2E3B2C)",
    "rose":       "soft dusty pink / muted salmon (hex #D4BABA)",
    "steelblue":  "cool muted steel blue (hex #8A979D)",
    "black":      "solid deep black (hex #17161A)",
}

# Material id → short English noun used inline as "{colour} {material}".
_MATERIAL_PL_TO_EN = {
    "knit":        "soft knit fabric",
    "boucle":      "bouclé fabric",
    "basketweave": "basketweave woven fabric",
    "chenille":    "chenille fabric",
    "ecoleather":  "eco-leather (faux leather)",
    "velour":      "velour fabric",
}

# Material id → rich texture/drape/features spec (from the TreeTale fabric
# matrix). Injected into the prompt's "Texture detail:" clause when the user
# hasn't typed their own material notes — see _build_generation_request.
_MATERIAL_TEXTURE_EN = {
    "knit":        "Soft, smooth knit with a subtle fine interlocking loop structure; medium weight, drapes softly and follows the furniture contours closely; matte finish, slightly stretchy appearance.",
    "boucle":      "Highly textured looped and curled yarns forming a nubby, irregular surface; heavy and bulky, holds its shape with a structured, substantial drape; matte finish, high dimensional depth, cozy and tactile.",
    "basketweave": "Distinctive woven texture with a visible interlaced thread pattern like a classic basketweave; medium-to-heavy weight, structured, slightly stiff and tailored drape; matte finish, durable classic look, visible thread contrast.",
    "chenille":    "Plush, velvety tufted-yarn surface, softly ribbed and caterpillar-like; medium-to-heavy weight, drapes smoothly with a soft, cozy, substantial feel; slight sheen that catches the light, rich and inviting.",
    "ecoleather":  "Smooth, slightly grained surface mimicking natural leather with a subtle uniform pore pattern; medium weight, structured and relatively stiff drape holding clean lines; slightly glossy, wipe-clean, modern and sleek.",
    "velour":      "Luxurious dense pile with a very soft, smooth, uniform surface and a subtle sheen; medium weight, elegant fluid soft and slightly-heavy fall; distinctive light-catching sheen, rich colour depth, subtle highlights and shadows.",
}

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
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Nano Sofa Studio v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Cap simultaneous Gemini calls within a single batch (variant set / photoshoot)
# so we never fire 8+ requests at one API key at once → self-induced 429/503.
# The anchor renders first (sequentially), then variants fan out through this
# gate. Created lazily so it binds to the running event loop; per-process.
_BATCH_CONCURRENCY = int(os.environ.get("BATCH_CONCURRENCY", "3"))
_gen_semaphore: Optional[asyncio.Semaphore] = None


def _batch_semaphore() -> asyncio.Semaphore:
    global _gen_semaphore
    if _gen_semaphore is None:
        _gen_semaphore = asyncio.Semaphore(_BATCH_CONCURRENCY)
    return _gen_semaphore


async def _capped(fn, *args):
    """Run blocking render `fn(*args)` in a thread, max _BATCH_CONCURRENCY at once."""
    async with _batch_semaphore():
        return await asyncio.to_thread(fn, *args)


# ---------------------------------------------------------------------------
# Structured error responses. Every failure path returns the same JSON shape so
# the frontend can render a typed error card (retry / fix-key / change-prompt)
# instead of dumping a raw exception string:
#   { error, error_code, detail_en, retryable, attempts? }
# ---------------------------------------------------------------------------
def _validation_error(message_pl: str, code: str, status: int = 400) -> JSONResponse:
    """A request-validation failure (bad/missing input) — never retryable."""
    return JSONResponse(
        {"error": message_pl, "error_code": code, "retryable": False},
        status_code=status,
    )


def _result_error(result, fallback: str = "Nieznany błąd generowania.") -> JSONResponse:
    """Structured response from a failed top-level GenerationResult."""
    return JSONResponse(
        {
            "error": result.error_message or fallback,
            "error_code": result.error_code or "UNKNOWN",
            "detail_en": result.error_detail,
            "retryable": bool(result.retryable),
            "attempts": result.attempts,
        },
        status_code=result.http_status or 500,
    )


def _item_error(base: dict, result_or_exc) -> dict:
    """Merge structured error fields into a per-item (variant / source) dict for
    the batch endpoints, classifying a raw gather exception when needed."""
    if isinstance(result_or_exc, Exception):
        info = classify_exception(result_or_exc)
        base.update(error=info.message_pl, error_code=info.error_code,
                    detail_en=str(result_or_exc), retryable=info.retryable)
    else:  # a GenerationResult
        r = result_or_exc
        base.update(error=r.error_message or "render failed",
                    error_code=r.error_code or "UNKNOWN",
                    detail_en=r.error_detail, retryable=bool(r.retryable))
    return base


_STATIC_DIR = _THIS  # serve prototype files from app-v2/

# OUTPUTS_DIR is the volume mount target in Docker. We keep generator outputs
# and per-request uploads under it so a single bind mount captures everything.
# Falls back to <repo>/outputs for local dev (matches the v1 layout).
_OUTPUT_DIR = Path(os.environ.get("OUTPUTS_DIR") or (_REPO_ROOT / "outputs")).resolve()
_UPLOAD_DIR = _OUTPUT_DIR / "v2-uploads"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Curated scene-reference images live alongside the app, baked into the Docker
# image at /app/app-v2/scene-references/<env_id>.{jpg,png,jpeg}. The lookup is
# best-effort — if no reference is found for an env_id, the prompt falls back
# to the text-only profile.
_SCENE_REFS_DIR = _THIS / "scene-references"


def _scene_reference_path(env_id: str) -> Optional[Path]:
    """Return the curated reference image path for an env id, if one exists."""
    if not env_id:
        return None
    for ext in (".jpg", ".jpeg", ".png"):
        candidate = _SCENE_REFS_DIR / f"{env_id}{ext}"
        if candidate.is_file():
            return candidate
    return None

# Override the generator's hardcoded outputs dir so it writes to the volume too.
# generator.py reads its dir at import time, so this must run before any call.
try:
    from app.core import generator as _gen_mod
    _gen_mod._OUTPUTS_DIR = _OUTPUT_DIR
except Exception:
    pass


@app.get("/")
def index():
    return FileResponse(_STATIC_DIR / "Nano Sofa Studio v2.html")


@app.get("/v1")
def index_v1():
    return FileResponse(_STATIC_DIR / "Nano Sofa Studio.html")


@app.get("/help")
def help_page():
    # /docs is taken by FastAPI's Swagger UI, so the user guide lives at /help.
    return FileResponse(_STATIC_DIR / "docs.html")


@app.get("/healthz")
def healthz():
    """
    Liveness + capability report. No external calls. Used by Docker HEALTHCHECK
    and by the frontend on boot to confirm the server is ready.
    """
    return {
        "ok": True,
        "model_ids": list(schema.model_ids),
        "outputs_dir": str(_OUTPUT_DIR),
        "n_outputs": sum(1 for p in _OUTPUT_DIR.glob("*.png")),
    }


@app.get("/api/config")
def api_config():
    """
    Returns the model enum + per-model constraints so the frontend can render
    the model picker and disable invalid resolution / refs combinations.
    Source of truth: prompts/schemas/sofa.json (via app.core.schema_loader).
    """
    models = []
    for mid in schema.model_ids:
        tier = "pro" if "pro" in mid else "flash"
        models.append({
            "id": mid,
            "label": mid,
            "tier": tier,
            "max_refs": schema.max_refs_for_model(mid),
            "max_resolution": schema.max_resolution_for_model(mid),
            "supports_resolution_param": schema.supports_resolution_param(mid),
            "resolutions": schema.resolution_choices_for_model(mid),
        })
    # Default model preference: prefer Nano Banana 2 (3.1-flash-image-preview)
    # for its richer scene adherence, 14-ref cap, and 4K resolution support
    # over the GA 2.5-flash-image (which deprecates 2026-10-02). Fall back to
    # the first model in the enum if 3.1 isn't available.
    preferred = "gemini-3.1-flash-image-preview"
    default_id = (
        preferred
        if any(m["id"] == preferred for m in models)
        else (models[0]["id"] if models else None)
    )
    return {
        "models": models,
        "default_model": default_id,
    }


@app.get("/api/eta")
def api_eta(model: str, resolution: str = "1K", refs: int = 0):
    """
    Estimated generation time for the given model/resolution/ref-count, so the
    frontend can show an honest ETA instead of a hardcoded constant. Returns
    measured p50/p90 from real history once enough renders accrue, otherwise a
    static seed estimate. Shape: {p50_s, p90_s, source, n}.
    """
    from app.core.cost_tracker import eta_for
    try:
        return eta_for(model, (resolution or "1K").split(" ")[0].strip().upper(), max(0, int(refs)))
    except Exception as exc:
        logger.warning("ETA lookup failed: %s", exc)
        return {"p50_s": 12.0, "p90_s": 24.0, "source": "fallback", "n": 0}


@app.get("/api/param-docs")
def api_param_docs():
    """
    Serialize the prompt mapping tables (the single source of truth for what
    each wizard parameter does) so the /help docs page can render, per option,
    the exact English clause the model receives. Keyed by the same id as the
    data.jsx NS_DATA tables, so the docs page joins these clauses with the
    Polish labels the UI shows — docs can't drift from behavior.
    """
    lens = {k: f"{v['focal_mm']} mm — {v['descriptor']}" for k, v in _LENS_TO_PROMPT.items()}
    shadow = {k: v["desc"] for k, v in _SHADOW_TO_PROMPT.items()}
    yaw = {k: f"{label} ({deg}° od osi)" for k, (label, deg) in _YAW_TO_ANGLE.items()}
    dof = {k: f"przysłona {v}" for k, v in _DOF_TO_APERTURE.items()}
    env = {k: f"[{mode}] {desc}" for k, (mode, desc) in _ENV_TO_SCENE.items()}

    groups = [
        {"key": "color",    "title": "Kolor obicia",        "table": "COLORS",        "clauses": dict(_COLOR_PL_TO_EN)},
        {"key": "material", "title": "Materiał",            "table": "MATERIALS",     "clauses": dict(_MATERIAL_PL_TO_EN)},
        {"key": "env",      "title": "Tło / sceneria",      "table": "ENVIRONMENTS",  "clauses": env},
        {"key": "shot",     "title": "Typ kadru",           "table": "SHOT_TYPES",    "clauses": dict(_SHOT_TYPE_TO_FRAMING)},
        {"key": "yaw",      "title": "Obrót / kąt kamery",  "table": "CAMERA_YAWS",   "clauses": yaw},
        {"key": "height",   "title": "Wysokość kamery",     "table": "CAMERA_HEIGHTS","clauses": dict(_HEIGHT_TO_PHRASE)},
        {"key": "dof",      "title": "Głębia ostrości",     "table": "DEPTHS_OF_FIELD","clauses": dof},
        {"key": "lens",     "title": "Obiektyw",            "table": "LENSES",        "clauses": lens},
        {"key": "tod",      "title": "Pora dnia / światło", "table": "TIMES_OF_DAY",  "clauses": dict(_TOD_TO_PROMPT)},
        {"key": "shadow",   "title": "Cień",                "table": "SHADOWS",       "clauses": shadow},
        {"key": "detail_fabric", "title": "Detal — makro tkaniny", "table": "DETAIL_REGIONS_FABRIC", "clauses": dict(_DETAIL_REGION_TO_PHRASE)},
        {"key": "detail_corner", "title": "Detal — narożnik / szew", "table": "DETAIL_REGIONS_CORNER", "clauses": dict(_DETAIL_REGION_TO_PHRASE)},
        {"key": "bedding",  "title": "Pościel (łóżka)",     "table": "BEDDING_PRESETS","clauses": dict(_BEDDING_TO_PROMPT)},
        {"key": "throw",    "title": "Narzuta / koc",       "table": "THROW_PRESETS", "clauses": dict(_THROW_TO_PROMPT)},
        {"key": "tidy",     "title": "Zaścielenie",         "table": "TIDY_LEVELS",   "clauses": dict(_TIDY_TO_PROMPT)},
        {"key": "density",  "title": "Gęstość stylizacji",  "table": "DENSITY_LEVELS","clauses": dict(_DENSITY_TO_PROMPT)},
        {"key": "accents",  "title": "Dodatki dekoracyjne", "table": "BED_ACCENTS",   "clauses": dict(_ACCENT_TO_PROMPT)},
    ]
    return {"groups": groups}


@app.get("/api/outputs/{name}")
def get_output(name: str):
    # Basename-only + parent check prevents path traversal (e.g. "../../etc/..."
    # or an absolute name) — this route only ever serves files that live
    # directly in _OUTPUT_DIR.
    candidate = (_OUTPUT_DIR / Path(name).name).resolve()
    if candidate.parent != _OUTPUT_DIR or not candidate.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(candidate, media_type=_MEDIA_TYPES.get(candidate.suffix.lower()))


def _build_generation_request(
    *,
    api_key: str,
    kind: str,
    color: str, color_custom: str,
    mat: str, mat_notes: str,
    size: str,
    legs: str,
    cam: str,
    lens: str, tod: str, shadow: str,
    env: str, env_note: str, env_mode: str,
    model: str, aspect: str, res: str, seed: str,
    base_image_path: Path,
    scene_image_path: Optional[Path],
    preserve_camera_from_base: bool = False,
    strict_in_place_recolor: bool = False,
    keep_source_scene: bool = False,
    extra_reference_paths: Optional[list[Path]] = None,
    lock_to_reference: bool = False,
    bedding_description: str = "",
    # New structured camera fields. When `shot` is empty, the old `cam`
    # preset is used as a fallback (back-compat with older form posts and
    # the batch / photoshoot paths that haven't been migrated yet).
    shot: str = "",
    yaw: str = "",
    height: str = "",
    dof: str = "",
    detail_region: str = "",
) -> GenerationRequest:
    """
    Translate a parsed FormData payload into a GenerationRequest.
    Shared by /api/generate (single render) and /api/generate-set (color batch).
    Resolves legacy Polish strings via the alias tables so stale browser caches
    keep working.
    """
    upholstery_color = (
        color_custom.strip()
        if color == "custom" and color_custom.strip()
        else _COLOR_PL_TO_EN.get(color, "neutral")
    )
    upholstery_material = _MATERIAL_PL_TO_EN.get(mat, "fabric")

    is_bed = kind == "bed"
    sofa_config = (_BED_CONFIG if is_bed else _SOFA_CONFIG).get(size, "3-seater")

    # ---- Resolve structured camera fields ---------------------------- #
    # If the new `shot` field is missing, derive shot/yaw/height from the
    # legacy `cam` preset. The new UI sends both `cam` (preset) and the
    # structured fields explicitly so users can override the preset.
    preset_shot, preset_yaw, preset_height = _CAM_PRESET_TO_STRUCTURED.get(
        cam, ("hero", "34_left", "eye")
    )
    shot_id   = shot.strip()   or preset_shot
    yaw_id    = yaw.strip()    or preset_yaw
    height_id = height.strip() or preset_height
    dof_id    = dof.strip()    or ("macro_shallow" if shot_id.startswith("detail_") else "standard")

    is_detail = shot_id in ("detail_fabric", "detail_corner")
    is_close_up = shot_id == "close_up"
    # Detail shots force a macro lens unless the user explicitly picked one
    # of the longer focal lengths. A 35 mm wide on a detail crop produces a
    # weirdly perspective-distorted macro that doesn't read as a real shot.
    if is_detail and lens.strip() in ("", "35mm_wide", "50mm_natural"):
        lens = "100mm_macro"

    camera_angle, deg = _YAW_TO_ANGLE.get(yaw_id, ("front-34-left", 35))

    # Build framing string from shot type + (optional) region.
    # Region selection rules:
    #   detail_fabric  → DETAIL_REGIONS_FABRIC  (default: weave)
    #   detail_corner  → DETAIL_REGIONS_CORNER  (default: arm_back_corner)
    #   close_up + bed → CLOSE_REGIONS_BED      (default: bed_corner_head)
    #   close_up + sofa→ CLOSE_REGIONS_SOFA     (default: sofa_corner)
    #   other          → no region
    if is_detail:
        default_region = (
            _DETAIL_REGION_DEFAULT_FABRIC if shot_id == "detail_fabric"
            else _DETAIL_REGION_DEFAULT_CORNER
        )
        region_id = detail_region.strip() or default_region
        region_phrase = _DETAIL_REGION_TO_PHRASE.get(
            region_id, _DETAIL_REGION_TO_PHRASE[default_region]
        )
    elif is_close_up:
        default_region = _CLOSE_REGION_DEFAULT_BED if is_bed else _CLOSE_REGION_DEFAULT_SOFA
        region_id = detail_region.strip() or default_region
        # Guard against cross-product region pick (e.g. sofa region with bed
        # product, or vice versa) by falling back to the product's default.
        valid_prefix = "bed_" if is_bed else "sofa_"
        if not region_id.startswith(valid_prefix):
            region_id = default_region
        region_phrase = _DETAIL_REGION_TO_PHRASE.get(
            region_id, _DETAIL_REGION_TO_PHRASE[default_region]
        )
    else:
        region_phrase = ""
    framing_template = _SHOT_TYPE_TO_FRAMING.get(shot_id, _SHOT_TYPE_TO_FRAMING["hero"])
    framing_str = framing_template.format(region=region_phrase) if "{region}" in framing_template else framing_template
    # Append camera-height phrase for non-detail shots (at macro distance
    # height isn't visually relevant — the crop fills the frame regardless).
    if not is_detail:
        height_phrase = _HEIGHT_TO_PHRASE.get(height_id, "")
        if height_phrase:
            framing_str = f"{framing_str}; {height_phrase}"

    aperture_str = _DOF_TO_APERTURE.get(dof_id, "f/4.5")

    lens_id   = _resolve_id(lens,   _LENS_LEGACY_ALIAS)
    tod_id    = _resolve_id(tod,    _TOD_LEGACY_ALIAS)
    shadow_id = _resolve_id(shadow, _SHADOW_LEGACY_ALIAS)

    lens_data       = _LENS_TO_PROMPT.get(lens_id, _LENS_DEFAULT)
    shadow_data     = _SHADOW_TO_PROMPT.get(shadow_id, _SHADOW_DEFAULT)
    tod_description = _TOD_TO_PROMPT.get(tod_id, "")
    env_mode_label, env_description = _ENV_TO_SCENE.get(env, ("packshot", "neutral grey studio backdrop"))

    res_token = (res or "1K").split(" ")[0].strip().upper()
    resolution = res_token if res_token in ("1K", "2K", "4K") else "1K"

    leg_count = 0 if is_bed and legs == "keep" else 4
    leg_id = _LEG_TO_ID.get(legs)

    notes_parts = []
    if env_note.strip(): notes_parts.append(f"environment note: {env_note.strip()}")
    if env_mode.strip(): notes_parts.append(f"environment use: {env_mode.strip()}")
    if seed.strip():     notes_parts.append(f"seed hint: {seed.strip()}")

    return GenerationRequest(
        model_id=model,
        base_product_image=str(base_image_path),
        scene_reference_image=str(scene_image_path) if scene_image_path else None,
        extra_reference_images=[str(p) for p in (extra_reference_paths or [])],
        lock_to_reference=lock_to_reference,
        product_type="bed" if is_bed else "sofa",
        sofa_configuration=sofa_config,
        leg_count=leg_count,
        preserve_list=["frame_silhouette", "stitching"],
        upholstery_color=upholstery_color,
        upholstery_material=upholstery_material,
        # User's own notes win; otherwise fall back to the fabric's matrix spec.
        texture_notes=(mat_notes.strip() or _MATERIAL_TEXTURE_EN.get(mat, "")),
        leg_id=leg_id,
        camera_angle=camera_angle,
        angle_degrees_from_left=deg,
        shadow_direction=shadow_data["direction"],
        focal_length_mm=lens_data["focal_mm"],
        aperture=aperture_str,
        framing=framing_str,
        shot_type=shot_id,
        detail_region_phrase=region_phrase,
        lens_descriptor=lens_data["descriptor"],
        tod_description=tod_description,
        shadow_description=shadow_data["desc"],
        env_mode=env_mode_label,
        env_description=env_description,
        preserve_camera_from_base=preserve_camera_from_base,
        strict_in_place_recolor=strict_in_place_recolor,
        keep_source_scene=keep_source_scene,
        bedding_description=bedding_description.strip(),
        aspect_ratio=aspect,
        resolution=resolution,
        notes=" | ".join(notes_parts),
        api_key=api_key.strip(),
    )


def _decode_and_save(raw: bytes, suffix: str) -> Path:
    """CPU-bound PIL decode/encode. Runs in a worker thread, never on the loop."""
    pil = Image.open(io.BytesIO(raw))
    pil.load()
    out = _UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}.png"
    pil.convert("RGB").save(out, format="PNG")
    return out


async def _save_upload(upload: UploadFile, suffix: str = "") -> Path:
    """Read an UploadFile, decode as image, save as PNG under the uploads dir.

    The blocking PIL decode/encode is off-loaded to a thread so a large upload
    can't stall the event loop (and with it /healthz and every other request).
    """
    raw = await upload.read()
    return await asyncio.to_thread(_decode_and_save, raw, suffix)


# ---------------------------------------------------------------------------
# Output format / size optimization
# ---------------------------------------------------------------------------
# Envs that emit a transparent-background render (alpha). JPEG can't hold alpha,
# so a JPG request for these is downgraded to WebP (which keeps alpha + stays
# small). Source of truth: the transparent cyclorama profile in _ENV_TO_SCENE.
_TRANSPARENT_ENVS = {"cyclorama_transparent", "transparent"}

_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
    ".mp4": "video/mp4", ".webm": "video/webm",
}


def _parse_quality(raw: str, default: int = 82) -> int:
    """Clamp a user-supplied quality string to a sane JPEG/WebP range."""
    try:
        q = int(float(raw))
    except (TypeError, ValueError):
        return default
    return max(40, min(100, q))


def _exif_bytes_from_png(img: Image.Image) -> Optional[bytes]:
    """Pack a master PNG's nano_sofa_* tEXt metadata into an EXIF block so the
    identity survives into the delivered JPEG/WebP (PNG text chunks don't carry
    over to those formats). Stored as compact JSON in ImageDescription (0x010E),
    with Software (0x0131) as a marker. Returns None when the master has no id."""
    text = getattr(img, "text", None) or {}
    gid = text.get("nano_sofa_generation_id")
    if not gid:
        return None
    payload = {
        "generation_id": gid,
        "model": text.get("nano_sofa_model", ""),
        "resolution": text.get("nano_sofa_resolution", ""),
        "color": text.get("nano_sofa_color", ""),
        "material": text.get("nano_sofa_material", ""),
        "summary": text.get("nano_sofa_prompt_summary", ""),
    }
    exif = Image.Exif()
    exif[0x010E] = "nano-sofa " + json.dumps(payload, ensure_ascii=False)
    exif[0x0131] = "Nano Sofa Studio v2"
    try:
        return exif.tobytes()
    except Exception:
        return None


def _derive_output(master: Path, fmt: str, quality: int, transparent: bool) -> tuple[Path, str, bool]:
    """
    From the lossless PNG `master`, write the user-facing delivery file in
    `fmt` (jpg|png|webp) and return (path, fmt_used, downgraded).

    The master is never mutated — it stays the lossless reference used by the
    variant/photoshoot pixel-lock chain. For png we just serve the master.
    JPEG has no alpha, so a transparent render asked for as jpg is transparently
    downgraded to WebP (keeps alpha, still ~5x smaller than PNG).
    """
    fmt = (fmt or "jpg").lower().strip()
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt not in ("jpg", "png", "webp"):
        fmt = "jpg"

    downgraded = False
    if fmt == "jpg" and transparent:
        fmt = "webp"
        downgraded = True

    if fmt == "png":
        return master, "png", False  # master is already an optimized PNG

    img = Image.open(master)
    img.load()
    # Carry the master's embedded id into the delivery file (EXIF) so downloads
    # and re-imports stay identifiable. Read before any mode conversion below.
    meta_exif = _exif_bytes_from_png(img)
    save_kwargs = {"exif": meta_exif} if meta_exif else {}
    out = master.with_suffix("." + fmt)
    if fmt == "jpg":
        # Flatten any alpha onto white before JPEG (no alpha channel in JPEG).
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            img = bg
        img.convert("RGB").save(out, format="JPEG", quality=quality, optimize=True, progressive=True, **save_kwargs)
    else:  # webp — keeps alpha if present
        img.save(out, format="WEBP", quality=quality, method=6, **save_kwargs)
    return out, fmt, downgraded


async def _derived_url(master: Path, fmt: str, quality: int, transparent: bool) -> tuple[str, str, bool]:
    """Derive the delivery file off the event loop and return its public URL."""
    derived, fmt_used, downgraded = await asyncio.to_thread(
        _derive_output, master, fmt, quality, transparent
    )
    return f"/api/outputs/{derived.name}", fmt_used, downgraded


# ---------------------------------------------------------------------------
# Storage retention — keep the outputs volume from growing without bound. Best
# effort: never raises, never blocks a response (run via asyncio.to_thread).
# ---------------------------------------------------------------------------
_MAX_OUTPUT_FILES = int(os.environ.get("MAX_OUTPUT_FILES", "800"))
_MAX_UPLOAD_FILES = int(os.environ.get("MAX_UPLOAD_FILES", "200"))


def _prune_dir(directory: Path, keep_newest: int) -> int:
    try:
        files = [p for p in directory.iterdir() if p.is_file()]
    except Exception:
        return 0
    if len(files) <= keep_newest:
        return 0
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for p in files[keep_newest:]:
        try:
            p.unlink()
            removed += 1
        except Exception:
            pass
    return removed


def _prune_storage() -> None:
    """Trim outputs + uploads to their newest-N caps. Masters and their derived
    siblings share an mtime, so they prune together."""
    try:
        n_out = _prune_dir(_OUTPUT_DIR, _MAX_OUTPUT_FILES)
        n_up = _prune_dir(_UPLOAD_DIR, _MAX_UPLOAD_FILES)
        if n_out or n_up:
            logger.info("Storage prune: removed %d output(s), %d upload(s)", n_out, n_up)
    except Exception as exc:  # never let cleanup break a request
        logger.warning("Storage prune skipped: %s", exc)


@app.post("/api/generate")
async def api_generate(
    api_key: str = Form(""),
    kind: str = Form("sofa"),
    color: str = Form("greige"),
    color_custom: str = Form(""),
    mat: str = Form("boucle"),
    mat_notes: str = Form(""),
    size: str = Form("3"),
    legs: str = Form("keep"),
    cam: str = Form("studio"),
    lens: str = Form("50mm_natural"),
    tod: str = Form("noon_neutral"),
    shadow: str = Form("soft_diffuse"),
    # New structured camera fields — see _build_generation_request for the
    # mapping tables. Empty values fall back to the `cam` preset.
    shot: str = Form(""),
    yaw: str = Form(""),
    height: str = Form(""),
    dof: str = Form(""),
    detail_region: str = Form(""),
    env: str = Form(""),
    env_note: str = Form(""),
    env_mode: str = Form(""),
    model: str = Form("gemini-2.5-flash-image"),
    aspect: str = Form("4:3"),
    res: str = Form("1K"),
    seed: str = Form(""),
    output_format: str = Form("jpg"),
    output_quality: str = Form("82"),
    base_image: Optional[UploadFile] = File(None),
    scene_image: Optional[UploadFile] = File(None),
    references: list[UploadFile] = File(default_factory=list),
    refs_lock: str = Form(""),
    preserve_base: str = Form(""),
    bedding: str = Form(""),
    bedding_custom: str = Form(""),
    throw: str = Form(""),
    tidy: str = Form(""),
    density: str = Form(""),
    accents: str = Form(""),
    bed_note: str = Form(""),
):
    if not api_key.strip():
        return _validation_error("Brak klucza API.", "MISSING_API_KEY")
    if base_image is None:
        return _validation_error("Brak zdjęcia bazowego.", "MISSING_BASE_IMAGE")

    try:
        upload_path = await _save_upload(base_image)
    except Exception as exc:
        return _validation_error(f"Nie udało się odczytać obrazu: {exc}", "BAD_INPUT_IMAGE")

    scene_upload_path: Optional[Path] = None
    if scene_image is not None:
        try:
            scene_upload_path = await _save_upload(scene_image, suffix="_scene")
        except Exception as exc:
            logger.warning("Scene reference image unreadable, ignoring: %s", exc)

    # Optional moodboard references from section 09 "Referencje". Each one that
    # can't be decoded is skipped with a warning rather than failing the whole
    # request — a malformed jpg in slot 3 shouldn't block the render.
    extra_ref_paths: list[Path] = []
    for idx, ref in enumerate(references or []):
        if ref is None:
            continue
        try:
            extra_ref_paths.append(await _save_upload(ref, suffix=f"_ref{idx}"))
        except Exception as exc:
            logger.warning("Reference #%d unreadable, ignoring: %s", idx, exc)

    bedding_desc = ""
    if kind == "bed":
        bedding_desc = _compose_bedding_description(
            bedding=bedding,
            bedding_custom=bedding_custom,
            throw=throw,
            tidy=tidy,
            density=density,
            accents_csv=accents,
            bed_note=bed_note,
        )

    req = _build_generation_request(
        api_key=api_key, kind=kind,
        color=color, color_custom=color_custom,
        mat=mat, mat_notes=mat_notes,
        size=size, legs=legs, cam=cam,
        lens=lens, tod=tod, shadow=shadow,
        shot=shot, yaw=yaw, height=height, dof=dof, detail_region=detail_region,
        env=env, env_note=env_note, env_mode=env_mode,
        model=model, aspect=aspect, res=res, seed=seed,
        base_image_path=upload_path,
        scene_image_path=scene_upload_path,
        extra_reference_paths=extra_ref_paths,
        lock_to_reference=refs_lock.strip().lower() in ("1", "true", "on", "yes"),
        preserve_camera_from_base=preserve_base.strip().lower() in ("1", "true", "on", "yes"),
        bedding_description=bedding_desc,
    )

    logger.info("Generating: %s / %s / %s", req.upholstery_color, req.upholstery_material, req.camera_angle)
    # Off-load the blocking Gemini call (network I/O + up to ~14s of retry
    # backoff) to a thread so the event loop stays responsive — /healthz, the
    # static assets, and other users' renders no longer freeze behind this one.
    # Matches what /api/generate-set and /api/generate-photoshoot already do.
    result = await asyncio.to_thread(generate, req)

    if not result.success or result.output_path is None:
        return _result_error(result)

    # Derive the user-facing download file (default JPG) off the lossless PNG
    # master, then trim the storage volume. The master is kept for reference reuse.
    image_url, fmt_used, downgraded = await _derived_url(
        result.output_path, output_format, _parse_quality(output_quality),
        env in _TRANSPARENT_ENVS,
    )
    await asyncio.to_thread(_prune_storage)

    return {
        "success": True,
        "generation_id": result.generation_id,
        "image_url": image_url,
        "format": fmt_used,
        "format_downgraded": downgraded,
        "cost": result.actual_cost,
        "model": result.model_id,
        "resolution": result.resolution,
        "elapsed_ms": result.elapsed_ms,
    }


@app.post("/api/generate-set")
async def api_generate_set(
    api_key: str = Form(""),
    kind: str = Form("sofa"),
    colors_csv: str = Form(""),     # comma-separated English color ids (anchor first)
    # Optional materials, paired positionally with colors_csv. Empty → fall
    # back to a single shared `mat` for the whole batch (legacy behavior).
    # When non-empty but shorter than colors_csv, the trailing colors reuse
    # the LAST material in the list. When longer, the excess is ignored.
    materials_csv: str = Form(""),
    color_custom: str = Form(""),
    mat: str = Form("boucle"),
    mat_notes: str = Form(""),
    size: str = Form("3"),
    legs: str = Form("keep"),
    cam: str = Form("studio"),
    lens: str = Form("50mm_natural"),
    tod: str = Form("noon_neutral"),
    shadow: str = Form("soft_diffuse"),
    # Structured camera fields — same semantics as /api/generate. When empty
    # the server falls back to the legacy `cam` preset.
    shot: str = Form(""),
    yaw: str = Form(""),
    height: str = Form(""),
    dof: str = Form(""),
    detail_region: str = Form(""),
    env: str = Form(""),
    env_note: str = Form(""),
    env_mode: str = Form(""),
    # Bed-only styling fields. The bedding description is composed once and
    # reused for every variant — styling shouldn't drift across a color set.
    bedding: str = Form(""),
    bedding_custom: str = Form(""),
    throw: str = Form(""),
    tidy: str = Form(""),
    density: str = Form(""),
    accents: str = Form(""),
    bed_note: str = Form(""),
    model: str = Form("gemini-3.1-flash-image-preview"),
    aspect: str = Form("4:3"),
    res: str = Form("1K"),
    seed: str = Form(""),
    output_format: str = Form("jpg"),
    output_quality: str = Form("82"),
    base_image: Optional[UploadFile] = File(None),
    scene_image: Optional[UploadFile] = File(None),
):
    """
    Generate a color-variant set with consistent scene/background.

    Strategy: render the FIRST color (anchor) normally, then fan out variants
    2..N in parallel using the anchor as BOTH a scene reference image (locks
    the pixel-level background) AND multi-turn history (preserves frame
    identity via Gemini's thought signatures). This combines the two
    documented Gemini mechanisms for identity-preserving edits.

    Returns: {
      anchor:   { color, image_url, cost, ... },
      variants: [{ color, image_url, cost, ... } | { color, error }, ...]
    }
    """
    if not api_key.strip():
        return _validation_error("Brak klucza API.", "MISSING_API_KEY")
    if base_image is None:
        return _validation_error("Brak zdjęcia bazowego.", "MISSING_BASE_IMAGE")

    color_ids = [c.strip() for c in colors_csv.split(",") if c.strip()]
    if len(color_ids) < 2:
        return _validation_error(
            "Wybierz co najmniej 2 kolory dla zestawu wariantów.", "TOO_FEW_COLORS"
        )
    if len(color_ids) > 8:
        return _validation_error(
            "Limit zestawu to 8 kolorów na jeden run.", "TOO_MANY_COLORS"
        )

    try:
        base_path = await _save_upload(base_image)
    except Exception as exc:
        return _validation_error(f"Nie udało się odczytać obrazu: {exc}", "BAD_INPUT_IMAGE")

    # Optional user-supplied scene reference (independent of the auto-anchor flow).
    scene_path: Optional[Path] = None
    if scene_image is not None:
        try:
            scene_path = await _save_upload(scene_image, suffix="_scene")
        except Exception as exc:
            logger.warning("Scene reference image unreadable, ignoring: %s", exc)

    # Materials per variant, paired positionally with color_ids.
    #   - Empty materials_csv → every variant uses the shared `mat`.
    #   - Shorter than colors → last material extends to fill remaining slots.
    #   - Longer than colors → excess is dropped.
    raw_mats = [m.strip() for m in materials_csv.split(",") if m.strip()]
    if not raw_mats:
        material_ids = [mat] * len(color_ids)
    else:
        material_ids = list(raw_mats[:len(color_ids)])
        while len(material_ids) < len(color_ids):
            material_ids.append(raw_mats[-1])

    # Bed styling — compose once, reuse for anchor + every variant. Styling
    # is intentionally locked across the set (the whole point of a variant
    # set is to compare colors/materials on the same staging).
    bedding_desc = ""
    if kind == "bed":
        bedding_desc = _compose_bedding_description(
            bedding=bedding,
            bedding_custom=bedding_custom,
            throw=throw,
            tidy=tidy,
            density=density,
            accents_csv=accents,
            bed_note=bed_note,
        )

    # ------------------------------------------------------------------ #
    # 1. Anchor render — first color in the list.
    # ------------------------------------------------------------------ #
    anchor_color = color_ids[0]
    anchor_mat = material_ids[0]
    logger.info(
        "Variant set: anchor=%s/%s, then %d more (materials=%s)",
        anchor_color, anchor_mat, len(color_ids) - 1, material_ids,
    )

    anchor_req = _build_generation_request(
        api_key=api_key, kind=kind,
        color=anchor_color, color_custom=color_custom,
        mat=anchor_mat, mat_notes=mat_notes,
        size=size, legs=legs, cam=cam,
        lens=lens, tod=tod, shadow=shadow,
        shot=shot, yaw=yaw, height=height, dof=dof, detail_region=detail_region,
        env=env, env_note=env_note, env_mode=env_mode,
        model=model, aspect=aspect, res=res, seed=seed,
        base_image_path=base_path,
        scene_image_path=scene_path,
        bedding_description=bedding_desc,
    )

    anchor_result = await asyncio.to_thread(generate, anchor_req)

    if not anchor_result.success or anchor_result.output_path is None:
        return _result_error(anchor_result)

    transparent_env = env in _TRANSPARENT_ENVS
    qual = _parse_quality(output_quality)
    anchor_url, _afmt, _adn = await _derived_url(
        anchor_result.output_path, output_format, qual, transparent_env
    )
    anchor_payload = {
        "color": anchor_color,
        "material": anchor_mat,
        "image_url": anchor_url,
        "generation_id": anchor_result.generation_id,
        "cost": anchor_result.actual_cost,
        "model": anchor_result.model_id,
        "resolution": anchor_result.resolution,
    }

    # ------------------------------------------------------------------ #
    # 2. Variants 2..N — fan out in parallel. Each one:
    #    - uses the anchor's PNG as scene_reference_image (pixel-lock bg)
    #    - inherits anchor's prior_history (thought-signature identity)
    #    - changes only the upholstery color
    # ------------------------------------------------------------------ #
    anchor_history = anchor_result.next_history

    def _render_variant(color_id: str, material_id: str):
        # Build a request mirroring the anchor, then mutate color + material +
        # scene_reference_image + prior_history.
        v_req = _build_generation_request(
            api_key=api_key, kind=kind,
            color=color_id, color_custom=color_custom,
            mat=material_id, mat_notes=mat_notes,
            size=size, legs=legs, cam=cam,
            lens=lens, tod=tod, shadow=shadow,
            shot=shot, yaw=yaw, height=height, dof=dof, detail_region=detail_region,
            env=env, env_note=env_note, env_mode=env_mode,
            model=model, aspect=aspect, res=res, seed=seed,
            base_image_path=base_path,
            scene_image_path=anchor_result.output_path,  # anchor PNG locks the scene
            bedding_description=bedding_desc,
        )
        v_req = dataclass_replace(
            v_req,
            prior_history=list(anchor_history),
            turn_number=2,
        )
        return generate(v_req)

    variant_pairs = list(zip(color_ids[1:], material_ids[1:]))
    variant_results = await asyncio.gather(
        *(_capped(_render_variant, cid, mid) for cid, mid in variant_pairs),
        return_exceptions=True,
    )

    variants_payload = []
    for (cid, mid), r in zip(variant_pairs, variant_results):
        if isinstance(r, Exception):
            variants_payload.append(_item_error({"color": cid, "material": mid}, r))
            continue
        if not r.success or r.output_path is None:
            variants_payload.append(_item_error({"color": cid, "material": mid}, r))
            continue
        v_url, _vf, _vd = await _derived_url(r.output_path, output_format, qual, transparent_env)
        variants_payload.append({
            "color": cid,
            "material": mid,
            "image_url": v_url,
            "generation_id": r.generation_id,
            "cost": r.actual_cost,
        })

    await asyncio.to_thread(_prune_storage)
    total_cost = anchor_result.actual_cost + sum(
        v.get("cost", 0) for v in variants_payload if "cost" in v
    )

    return {
        "success": True,
        "anchor": anchor_payload,
        "variants": variants_payload,
        "total_cost": total_cost,
        "model": model,
    }


def _read_png_meta(path: Path) -> dict:
    """Read the nano_sofa_* tEXt chunks off a master PNG, best-effort."""
    try:
        with Image.open(path) as im:
            return dict(getattr(im, "text", {}) or {})
    except Exception:
        return {}


def _resolve_anchor_path(anchor_ref: str) -> Optional[Path]:
    """Resolve a client-supplied anchor reference to an on-disk master image.

    `anchor_ref` may be a full generation_id OR an /api/outputs basename (which
    can be a derived .jpg/.webp). Returns the lossless .png master when present
    (preferred for the pixel-lock), else the referenced file. Always constrained
    to _OUTPUT_DIR by basename — no path traversal, no client-supplied dirs.
    """
    ref = (anchor_ref or "").strip()
    if not ref:
        return None

    # 1. generation_id → look up the master in the cost DB, then re-home its
    # basename into _OUTPUT_DIR (the DB may hold a path from the v1 layout).
    db_path = output_path_for_generation(ref)
    if db_path:
        cand = (_OUTPUT_DIR / Path(db_path).name).resolve()
        if cand.parent == _OUTPUT_DIR and cand.is_file():
            return cand

    # 2. looks like a generation_id (uuid, no dot/slash) → match the filename
    # convention {ts}_{model}_{id[:8]}.png directly on disk, so a render still
    # resolves even when the DB has no row for it (stale/foreign DB).
    if "." not in ref and "/" not in ref and len(ref) >= 8:
        for cand in sorted(_OUTPUT_DIR.glob(f"*_{ref[:8]}.png")):
            cand = cand.resolve()
            if cand.parent == _OUTPUT_DIR and cand.is_file():
                return cand

    # 3. basename → prefer the .png master over a .jpg/.webp derivative.
    name = Path(ref).name
    for cand in (_OUTPUT_DIR / f"{Path(name).stem}.png", _OUTPUT_DIR / name):
        cand = cand.resolve()
        if cand.parent == _OUTPUT_DIR and cand.is_file():
            return cand
    return None


def _recolor_request(
    *, api_key, kind, color, color_custom, mat, mat_notes, size, legs, cam, lens,
    tod, shadow, shot, yaw, height, dof, detail_region, model, aspect, res, seed,
    bedding_desc, source_path,
):
    """One in-place recolor of `source_path`: keep its EXACT angle + background,
    change ONLY the upholstery colour/material. Drives the generator's
    keep_source_scene recolor mode — base image only (no scene reference), and the
    SCENE backdrop block is suppressed so the source's own background is preserved.
    This is the consistency fix for the old flow's colour-miss + background-drift."""
    return _build_generation_request(
        api_key=api_key, kind=kind,
        color=color, color_custom=color_custom,
        mat=mat, mat_notes=mat_notes,
        size=size, legs=legs, cam=cam,
        lens=lens, tod=tod, shadow=shadow,
        shot=shot, yaw=yaw, height=height, dof=dof, detail_region=detail_region,
        env="", env_note="", env_mode="",
        model=model, aspect=aspect, res=res, seed=seed,
        base_image_path=source_path,
        scene_image_path=None,                  # NO scene ref → model can't copy the old colour
        preserve_camera_from_base=True,
        strict_in_place_recolor=True,
        keep_source_scene=True,                 # keep the source photo's own background
        bedding_description=bedding_desc,
    )


# Fotosesja v2 grid limits (single-user localhost tool; bound cost + fan-out).
_MAX_SOURCES = 8
_MAX_PAIRS = 8
_MAX_GRID_RENDERS = 48


@app.post("/api/generate-variants")
async def api_generate_variants(
    api_key: str = Form(""),
    kind: str = Form("sofa"),
    # Shared colour+material PAIRS applied to EVERY source.
    # JSON: [{"color": "<chip id>", "material": "<chip id>"}, ...]
    pairs_json: str = Form(""),
    color_custom: str = Form(""),
    mat_notes: str = Form(""),
    size: str = Form("3"),
    legs: str = Form("keep"),
    cam: str = Form("studio"),
    lens: str = Form("50mm_natural"),
    tod: str = Form("noon_neutral"),
    shadow: str = Form("soft_diffuse"),
    shot: str = Form(""),
    yaw: str = Form(""),
    height: str = Form(""),
    dof: str = Form(""),
    detail_region: str = Form(""),
    bedding: str = Form(""),
    bedding_custom: str = Form(""),
    throw: str = Form(""),
    tidy: str = Form(""),
    density: str = Form(""),
    accents: str = Form(""),
    bed_note: str = Form(""),
    model: str = Form("gemini-3.1-flash-image-preview"),
    aspect: str = Form("4:3"),
    res: str = Form("1K"),
    seed: str = Form(""),
    output_format: str = Form("jpg"),
    output_quality: str = Form("82"),
    # Sources = base photos. Uploaded files AND/OR refs to existing renders.
    # Each carries a client sid (parallel csv) so results group back per source.
    sources: list[UploadFile] = File(default_factory=list),
    upload_sids_csv: str = Form(""),
    source_refs_csv: str = Form(""),
    ref_sids_csv: str = Form(""),
):
    """
    Fotosesja v2 — apply a shared set of colour+material PAIRS to MANY base photos.

    For every (source × pair) it runs an in-place recolor that keeps the source
    photo's exact angle and background (generator keep_source_scene mode), changing
    only the upholstery colour/material. Sources may be freshly uploaded photos or
    refs to existing renders (generation_id / output basename). Results are grouped
    by source so the UI can show one row per photo.

    Streams NDJSON (application/x-ndjson), one JSON object per line:
      {"type":"meta","total":N,"model":..,"sources":[{sid,source_kind,source_ref,source_url,error?}]}
      {"type":"tile","sid":..,"color":..,"material":..,"image_url"/"generation_id"/"cost" | "error"}  (one per completed render)
      {"type":"done","total_cost":..}
    Pre-flight validation errors are returned as a normal JSON 4xx BEFORE the stream starts.
    """
    if not api_key.strip():
        return _validation_error("Brak klucza API.", "MISSING_API_KEY")

    # ---- parse the shared colour+material pairs ------------------------- #
    try:
        raw_pairs = json.loads(pairs_json) if pairs_json.strip() else []
    except Exception:
        raw_pairs = []
    pairs = []
    for p in raw_pairs if isinstance(raw_pairs, list) else []:
        if not isinstance(p, dict):
            continue
        c = str(p.get("color", "")).strip()
        m = str(p.get("material", "")).strip() or "boucle"
        if c:
            pairs.append({"color": c, "material": m})
    if not pairs:
        return _validation_error("Dodaj co najmniej 1 parę kolor + materiał.", "TOO_FEW_PAIRS")
    if len(pairs) > _MAX_PAIRS:
        return _validation_error(f"Limit par kolor/materiał: {_MAX_PAIRS}.", "TOO_MANY_PAIRS")

    # ---- assemble the ordered source list (uploads, then refs) --------- #
    upload_sids = [s.strip() for s in upload_sids_csv.split(",")]
    ref_items = [r.strip() for r in source_refs_csv.split(",") if r.strip()]
    ref_sids = [s.strip() for s in ref_sids_csv.split(",")]

    resolved: list[dict] = []   # {sid, kind, ref, path|None, url|None, error?}
    for i, up in enumerate(sources or []):
        sid = upload_sids[i] if i < len(upload_sids) and upload_sids[i] else f"u{i}"
        try:
            p = await _save_upload(up, suffix="_src")
            resolved.append({"sid": sid, "kind": "upload", "ref": up.filename or "", "path": p, "url": None})
        except Exception as exc:
            resolved.append({"sid": sid, "kind": "upload", "ref": up.filename or "", "path": None,
                             "url": None, "error": f"Nie udało się odczytać zdjęcia: {exc}"})
    for j, ref in enumerate(ref_items):
        sid = ref_sids[j] if j < len(ref_sids) and ref_sids[j] else f"r{j}"
        path = _resolve_anchor_path(ref)
        if path is None:
            resolved.append({"sid": sid, "kind": "ref", "ref": ref, "path": None, "url": None,
                             "error": "Nie znaleziono zdjęcia (mogło zostać usunięte)."})
        else:
            resolved.append({"sid": sid, "kind": "ref", "ref": ref, "path": path,
                             "url": f"/api/outputs/{path.name}"})

    if not resolved:
        return _validation_error("Wybierz co najmniej 1 zdjęcie bazowe.", "MISSING_SOURCES")
    if len(resolved) > _MAX_SOURCES:
        return _validation_error(f"Limit zdjęć bazowych: {_MAX_SOURCES}.", "TOO_MANY_SOURCES")
    usable = [s for s in resolved if s.get("path")]
    if not usable:
        return _validation_error("Żadnego zdjęcia bazowego nie udało się wczytać.", "BAD_INPUT_IMAGE")
    if len(usable) * len(pairs) > _MAX_GRID_RENDERS:
        return _validation_error(
            f"Za dużo renderów ({len(usable)}×{len(pairs)}). Limit to {_MAX_GRID_RENDERS} na run.",
            "TOO_MANY_RENDERS",
        )

    bedding_desc = ""
    if kind == "bed":
        bedding_desc = _compose_bedding_description(
            bedding=bedding, bedding_custom=bedding_custom, throw=throw,
            tidy=tidy, density=density, accents_csv=accents, bed_note=bed_note,
        )
    qual = _parse_quality(output_quality)
    logger.info("Variant grid: %d sources × %d pairs", len(usable), len(pairs))

    # ---- stream every (source × pair) recolor as NDJSON ---------------- #
    # Pre-flight passed; now emit  meta → one `tile` per completed render → done.
    # The client fills the grid live and drives a real X/N progress bar so the
    # user sees first results immediately instead of waiting for the whole batch.
    def _render(src_path, pair):
        return generate(_recolor_request(
            api_key=api_key, kind=kind,
            color=pair["color"], color_custom=color_custom,
            mat=pair["material"], mat_notes=mat_notes,
            size=size, legs=legs, cam=cam, lens=lens, tod=tod, shadow=shadow,
            shot=shot, yaw=yaw, height=height, dof=dof, detail_region=detail_region,
            model=model, aspect=aspect, res=res, seed=seed,
            bedding_desc=bedding_desc, source_path=src_path,
        ))

    async def _job(s, pair):
        # Never raises — failures become an error tile so the stream stays intact.
        try:
            r = await _capped(_render, s["path"], pair)
        except Exception as exc:
            return s, _item_error({"color": pair["color"], "material": pair["material"]}, exc)
        if not r.success or r.output_path is None:
            return s, _item_error({"color": pair["color"], "material": pair["material"]}, r)
        v_url, _vf, _vd = await _derived_url(r.output_path, output_format, qual, False)
        return s, {"color": pair["color"], "material": pair["material"],
                   "image_url": v_url, "generation_id": r.generation_id, "cost": r.actual_cost}

    total = len(usable) * len(pairs)

    async def _stream():
        meta = {
            "type": "meta", "total": total, "model": model,
            "sources": [{"sid": s["sid"], "source_kind": s["kind"], "source_ref": s["ref"],
                         "source_url": s.get("url"), "error": s.get("error")} for s in resolved],
        }
        yield json.dumps(meta) + "\n"
        total_cost = 0.0
        coros = [_job(s, pair) for s in usable for pair in pairs]
        for fut in asyncio.as_completed(coros):
            s, tile = await fut
            if "cost" in tile:
                total_cost += tile.get("cost", 0)
            yield json.dumps({"type": "tile", "sid": s["sid"], **tile}) + "\n"
        await asyncio.to_thread(_prune_storage)
        yield json.dumps({"type": "done", "total_cost": total_cost}) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@app.post("/api/regenerate-variant")
async def api_regenerate_variant(
    api_key: str = Form(""),
    kind: str = Form("sofa"),
    color: str = Form(""),
    material: str = Form("boucle"),
    color_custom: str = Form(""),
    mat_notes: str = Form(""),
    size: str = Form("3"),
    legs: str = Form("keep"),
    cam: str = Form("studio"),
    lens: str = Form("50mm_natural"),
    tod: str = Form("noon_neutral"),
    shadow: str = Form("soft_diffuse"),
    shot: str = Form(""),
    yaw: str = Form(""),
    height: str = Form(""),
    dof: str = Form(""),
    detail_region: str = Form(""),
    bedding: str = Form(""),
    bedding_custom: str = Form(""),
    throw: str = Form(""),
    tidy: str = Form(""),
    density: str = Form(""),
    accents: str = Form(""),
    bed_note: str = Form(""),
    model: str = Form("gemini-3.1-flash-image-preview"),
    aspect: str = Form("4:3"),
    res: str = Form("1K"),
    seed: str = Form(""),
    output_format: str = Form("jpg"),
    output_quality: str = Form("82"),
    # Source: a ref to an existing render OR a re-uploaded base photo.
    source_ref: str = Form(""),
    source_image: Optional[UploadFile] = File(None),
):
    """Re-render ONE (source × colour+material) tile in the same keep-scene recolor
    mode. Backs the per-tile 'regeneruj' button so a single bad render can be fixed
    without re-running the whole grid."""
    if not api_key.strip():
        return _validation_error("Brak klucza API.", "MISSING_API_KEY")
    if not color.strip():
        return _validation_error("Brak koloru wariantu.", "TOO_FEW_PAIRS")

    src_path: Optional[Path] = None
    if source_ref.strip():
        src_path = _resolve_anchor_path(source_ref)
        if src_path is None:
            return _validation_error("Nie znaleziono zdjęcia bazowego.", "ANCHOR_NOT_FOUND", status=404)
    elif source_image is not None:
        try:
            src_path = await _save_upload(source_image, suffix="_src")
        except Exception as exc:
            return _validation_error(f"Nie udało się odczytać zdjęcia: {exc}", "BAD_INPUT_IMAGE")
    else:
        return _validation_error("Brak zdjęcia bazowego.", "MISSING_SOURCES")

    bedding_desc = ""
    if kind == "bed":
        bedding_desc = _compose_bedding_description(
            bedding=bedding, bedding_custom=bedding_custom, throw=throw,
            tidy=tidy, density=density, accents_csv=accents, bed_note=bed_note,
        )
    req = _recolor_request(
        api_key=api_key, kind=kind, color=color, color_custom=color_custom,
        mat=material, mat_notes=mat_notes, size=size, legs=legs, cam=cam,
        lens=lens, tod=tod, shadow=shadow, shot=shot, yaw=yaw, height=height,
        dof=dof, detail_region=detail_region, model=model, aspect=aspect, res=res,
        seed=seed, bedding_desc=bedding_desc, source_path=src_path,
    )
    result = await asyncio.to_thread(generate, req)
    if not result.success or result.output_path is None:
        return _result_error(result)
    qual = _parse_quality(output_quality)
    url, _f, _d = await _derived_url(result.output_path, output_format, qual, False)
    await asyncio.to_thread(_prune_storage)
    return {"success": True, "color": color, "material": material, "image_url": url,
            "generation_id": result.generation_id, "cost": result.actual_cost}


@app.get("/api/history")
def api_history(limit: int = 60):
    """Past renders on disk (newest first), self-describing via embedded metadata.

    Powers the Fotosesja "Historia" anchor browser. Read-only; no API key needed.
    Lists the master PNGs under _OUTPUT_DIR and reads each one's identity straight
    from its tEXt chunks (the embed written at generate time), enriching from the
    cost DB only for older files that predate the embed. This is robust to a
    stale/foreign cost DB — every file the user can see is pickable as an anchor.
    Each item is reusable via /api/generate-variants by its generation_id.
    """
    limit = max(1, min(int(limit or 60), 200))

    # Index the cost DB by output basename to enrich files lacking embedded meta.
    db_by_name: dict = {}
    try:
        for rec in recent_generations(800):
            op = rec.get("output_path")
            if op:
                db_by_name.setdefault(Path(op).name, rec)
    except Exception:
        pass

    # Master PNGs live directly under _OUTPUT_DIR (uploads are in a subdir;
    # derived jpg/webp aren't .png). Newest first by mtime.
    try:
        masters = [p for p in _OUTPUT_DIR.glob("*.png") if p.is_file()]
    except Exception:
        masters = []
    masters.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    items: list[dict] = []
    for p in masters[:limit]:
        meta = _read_png_meta(p)
        rec = db_by_name.get(p.name, {})
        ts_raw = meta.get("nano_sofa_ts", "")
        items.append({
            "generation_id": meta.get("nano_sofa_generation_id") or rec.get("generation_id"),
            "image_url": f"/api/outputs/{p.name}",
            "color": meta.get("nano_sofa_color") or rec.get("upholstery_color"),
            "material": meta.get("nano_sofa_material") or rec.get("upholstery_material"),
            "model": meta.get("nano_sofa_model") or rec.get("model_id"),
            "resolution": meta.get("nano_sofa_resolution") or rec.get("resolution"),
            "camera_angle": meta.get("nano_sofa_camera_angle") or rec.get("camera_angle"),
            "prompt_summary": meta.get("nano_sofa_prompt_summary") or rec.get("prompt_summary"),
            "ts": int(ts_raw) if ts_raw.isdigit() else rec.get("timestamp"),
        })
    return {"items": items}


# ---------------------------------------------------------------------------
# Video (Veo) — text-to-video, separate subpage from the sofa/bed image studio.
# ---------------------------------------------------------------------------
@app.get("/video")
def video_page():
    return FileResponse(_STATIC_DIR / "video.html")


@app.get("/api/video-models")
def api_video_models(api_key: str = ""):
    """
    Veo model catalog + per-model constraints for the video picker. When a key
    is supplied we probe the live API and keep only models that key can reach
    (falls back to the full catalog on any failure — the picker is never empty).
    """
    return list_video_models(api_key.strip())


@app.get("/api/video-diagnose")
def api_video_diagnose(api_key: str = ""):
    """
    Debug helper — what video models can this key actually see, and does a probe
    succeed? Helps answer "does my key have Veo access / is billing enabled".
    NOTE: models.list() usually lists models regardless of billing tier, so a
    visible Veo model does NOT guarantee generation works on a free tier.
    """
    from app.core.video_generator import VIDEO_MODELS  # noqa: PLC0415
    out: dict = {"probe_ok": False, "error": None, "total_models": 0,
                 "video_models_visible": [], "targets": {}}
    key = (api_key or "").strip()
    if not key:
        out["error"] = "Brak klucza."
        return out
    try:
        from google import genai
        from google.genai import types as gtypes
        client = genai.Client(api_key=key, http_options=gtypes.HttpOptions(timeout=30000))
        ids = []
        for m in client.models.list():
            nm = (getattr(m, "name", "") or "").split("/")[-1]
            if nm:
                ids.append(nm)
        out["probe_ok"] = True
        out["total_models"] = len(ids)
        low = lambda s: s.lower()
        out["video_models_visible"] = sorted(
            i for i in ids if any(k in low(i) for k in ("veo", "omni", "video"))
        )
        out["targets"] = {m["id"]: (m["id"] in ids) for m in VIDEO_MODELS}
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


@app.post("/api/generate-video")
async def api_generate_video(
    api_key: str = Form(""),
    prompt: str = Form(""),
    model: str = Form("veo-3.1-fast-generate-preview"),
    aspect: str = Form("16:9"),
    resolution: str = Form("720p"),
    duration: str = Form("8"),
    audio: str = Form("true"),
    negative_prompt: str = Form(""),
    seed: str = Form(""),
    image: Optional[UploadFile] = File(None),   # first-frame / reference (image-to-video)
):
    if not api_key.strip():
        return _validation_error("Brak klucza API.", "MISSING_API_KEY")
    if not prompt.strip():
        return _validation_error("Wpisz opis (prompt) filmu.", "INVALID_REQUEST")

    try:
        duration_i = int(str(duration).strip() or "8")
    except ValueError:
        duration_i = 8
    seed_i: Optional[int] = None
    if str(seed).strip():
        try:
            seed_i = int(str(seed).strip())
        except ValueError:
            seed_i = None

    # Optional starting-frame / reference image (image-to-video). Read the bytes
    # off the event loop and only pass real image data through.
    image_bytes: Optional[bytes] = None
    image_mime = "image/png"
    if image is not None and getattr(image, "filename", ""):
        raw = await image.read()
        if raw:
            ctype = (image.content_type or "").lower()
            if not ctype.startswith("image/"):
                return _validation_error(
                    "Klatka początkowa musi być obrazem (JPG / PNG / WebP).",
                    "INVALID_REQUEST",
                )
            image_bytes = raw
            image_mime = ctype or "image/png"

    req = VideoRequest(
        api_key=api_key.strip(),
        prompt=prompt.strip(),
        model_id=model.strip(),
        aspect_ratio=aspect.strip(),
        resolution=resolution.strip(),
        duration_seconds=duration_i,
        negative_prompt=negative_prompt.strip(),
        generate_audio=str(audio).strip().lower() in ("1", "true", "on", "yes"),
        seed=seed_i,
        image_bytes=image_bytes,
        image_mime=image_mime,
    )

    logger.info("Generating video: %s / %s / %ss", req.model_id, req.resolution, req.duration_seconds)
    result = await asyncio.to_thread(generate_video, req)

    if not result.success or not result.video_bytes:
        # error_detail carries the raw Gemini message — invaluable for telling a
        # bad param apart from a tier/access problem. Surfaced to the client.
        logger.warning("Video gen failed: %s | %s", result.error_code, result.error_detail)
        return JSONResponse(
            {
                "error": result.error_message or "Nie udało się wygenerować wideo.",
                "error_code": result.error_code or "UNKNOWN",
                "error_detail": result.error_detail or "",
                "retryable": result.retryable,
            },
            status_code=result.http_status or 500,
        )

    # Persist the mp4 alongside images so /api/outputs/{name} serves it and the
    # newest-N prune applies. The image history globs *.png, so videos don't
    # pollute it.
    short = req.model_id.replace("veo-", "").replace("-generate-preview", "").replace(".", "")
    name = f"video_{short}_{uuid.uuid4().hex[:8]}.mp4"
    out_path = _OUTPUT_DIR / name
    try:
        out_path.write_bytes(result.video_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to write video output: %s", exc)
        return JSONResponse(
            {"error": "Nie udało się zapisać pliku wideo na serwerze.",
             "error_code": "SERVER_MISCONFIG", "retryable": False},
            status_code=500,
        )
    await asyncio.to_thread(_prune_storage)

    return {
        "success": True,
        "video_url": f"/api/outputs/{name}",
        "mime_type": result.mime_type,
        "model": result.model_id,
        "resolution": result.resolution,
        "aspect": result.aspect_ratio,
        "duration": result.duration_seconds,
        "audio": result.audio,
        "engine": result.engine,
        "cost": result.estimated_cost_usd,
    }


# Static files for the prototype JS / CSS — mounted last so dynamic routes win.
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")


def main() -> None:
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 7861))
    log_level = os.environ.get("LOG_LEVEL", "info")
    logger.info("Nano Sofa v2 starting on http://%s:%d  (outputs=%s)", host, port, _OUTPUT_DIR)
    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
