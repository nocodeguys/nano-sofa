# legs/ — sofa leg reference library

This directory is the leg reference library for the nano-sofa generation pipeline. It contains:

- **3D-rendered PNG references** for each leg style × material × camera angle combination.
- **`manifest.json`** — the catalog the Gradio app reads to populate the leg picker.
- **`render-blender.py`** — the Blender batch-render script that produces all PNGs.
- **`STANDARDS.md`** — the rulebook for geometry, lighting, naming, and output format.
- **`ADDING-A-LEG.md`** — step-by-step instructions for adding a new leg style.
- **`source/`** — Blender `.blend` source files, one per leg style.

---

## Why this library exists

Most furniture generation pipelines describe legs in words. This pipeline renders them in 3D and attaches the render as a reference image in the generation request.

The research in `docs/research/nano-banana-state.md` identifies **leg-geometry-morphing** as the top failure mode in furniture product photography generation: the model blends adjacent leg styles rather than replacing cleanly. The primary mitigation is the **dual text+image signal** — a reference image of the exact leg geometry plus an explicit text descriptor (`explicit_descriptor` in the manifest) sent together in the same prompt. This library makes that signal consistent, reproducible, and angle-matched to the camera used for each sofa generation request.

---

## Quick orientation

### The manifest

`manifest.json` is the single source of truth for what legs are available. Each entry has:

- `id` — the lookup key used in `prompts/schemas/sofa.json` under `variant.legs.reference`.
- `explicit_descriptor` — the text sent to the model alongside the reference image.
- `renders` — paths to the rendered PNG for each angle slug.
- `geometry` — structured dimensions (height, width, presence of braces, attachment type).
- `tags` — style family tags for filtering in the Gradio app.
- `shadow_direction_hint` — the clock-position of the contact shadow from the standard render rig (used to populate `camera.shadow_direction` in generation requests).

### The naming convention

```
<style>_<material>_<angle>.png
```

All slugs are lowercase, one token each (no hyphens within a slug). Examples:

- `tapered_walnut_front34l.png`
- `hairpin_blacksteel_side90.png`
- `plinth_oak_low34.png`
- `splayedtaper_brass_front34r_alpha.png`  ← alpha variant

### The five canonical angles

| Slug | Matches schema `camera.angle` | Description |
|---|---|---|
| `front0` | `front-0` | Dead-on front |
| `front34l` | `front-34-left` | 34° left of front |
| `front34r` | `front-34-right` | 34° right of front |
| `side90` | `side-90` | Pure profile |
| `low34` | `low-34` | Low camera, upward tilt |

The Gradio app selects the angle-matched render (the `front34l` PNG when the sofa is photographed at `front-34-left`, etc.) before assembling the reference slots for the generation request.

---

## First-batch leg styles (v0.2.0)

| ID | Style | Material | Height | Notes |
|---|---|---|---|---|
| `tapered_walnut` | tapered | solid walnut, satin | 12 cm | Most common sofa leg — scandi, mid-century |
| `tapered_oak` | tapered | solid oak, natural | 12 cm | Lighter warm-wood variant |
| `tapered_mattewhite` | tapered | matte white | 12 cm | Contemporary all-white builds |
| `hairpin_blacksteel` | hairpin | black powder-coated steel | 15 cm | Industrial, retro |
| `hairpin_brass` | hairpin | brushed brass | 15 cm | Glam, art-deco |
| `hairpin_chrome` | hairpin | polished chrome | 15 cm | Cool contemporary |
| `plinth_oak` | plinth | solid oak | 8 cm | Continuous skirting, japandi |
| `plinth_mattewhite` | plinth | matte white | 8 cm | Contemporary minimal |
| `bun_walnut` | bun | solid walnut | 10 cm | Traditional, English classic |
| `bun_oak` | bun | solid oak | 10 cm | Traditional, lighter variant |
| `block_oak` | block | solid oak | 12 cm | Japandi, architectural |
| `block_walnut` | block | solid walnut | 12 cm | Dark japandi |
| `splayedtaper_walnut` | splayedtaper | solid walnut, satin | 17 cm | Mid-century, splayed outward |
| `splayedtaper_oak` | splayedtaper | solid oak, natural | 17 cm | Scandi mid-century |
| `turned_walnut` | turned | solid walnut, satin | 14 cm | Traditional turned, decorative rings |
| `turned_oak` | turned | solid oak, natural | 14 cm | Country, cottage |
| `cabriole_walnut` | cabriole | solid walnut, satin | 16 cm | Georgian, Chippendale — asymmetric |
| `squaretaper_blacksteel` | squaretaper | black powder-coated steel | 12 cm | Contemporary geometric |
| `squaretaper_brass` | squaretaper | brushed brass | 12 cm | Glam geometric |

All renders are pending — the `renders` objects in the manifest are empty until the Blender render script is run against the corresponding `.blend` source files.

---

## Sourcing strategy for 3D models

The first-batch styles are all **procedural** — built directly in Blender without downloading any third-party assets. This keeps the library fully CC0 with no attribution requirements and no external dependencies.

Procedural construction routes per style family:

| Style | Blender technique |
|---|---|
| tapered, splayedtaper | Cylinder with vertex-group taper via proportional edit, or a profile curve + spin |
| hairpin | Circle-profile curve bent into a hairpin path using the curve modifier |
| plinth | Box mesh with bevelled lower edge |
| bun | Spin modifier on an oblate profile curve |
| block | Cube mesh scaled to spec |
| turned | Spin modifier on a decorative turned-leg profile curve |
| cabriole | Curve object defining the S-profile, extruded |
| squaretaper | Cube with per-face shear or simple vertex scaling |

For future non-procedural additions, see `ADDING-A-LEG.md` for BlenderKit and Sketchfab sourcing steps.

---

## How the Gradio app uses this library

1. On startup, the app reads `legs/manifest.json` and populates the leg picker dropdown with all available entries, grouped by style family.
2. When the user selects a leg and submits a generation request, the app:
   a. Reads `camera.angle` from the request.
   b. Maps the angle to the corresponding render PNG from `renders[angle_slug].main`.
   c. Attaches the PNG as `reference_slots.slot_2_leg_reference` (always slot 2, per the schema).
   d. Populates `variant.legs.explicit_descriptor` from the manifest entry's `explicit_descriptor` field.
   e. Populates `camera.shadow_direction` from `shadow_direction_hint` if not already set by the user.
3. The assembled prompt includes both the reference image and the explicit_descriptor text — the dual signal that mitigates leg-geometry-morphing.

---

## Schema compatibility

This library is built against `prompts/schemas/sofa.json` v0.2.0. The relevant fields:

| Schema field | Source in this library |
|---|---|
| `reference_slots.slot_2_leg_reference` | Manifest `id` field |
| `variant.legs.reference` | Manifest `id` field |
| `variant.legs.explicit_descriptor` | Manifest `explicit_descriptor` field |
| `camera.shadow_direction` | Manifest `shadow_direction_hint` field |
| `product.leg_count` | Set per sofa product, not per leg library entry |

---

## Ownership rule

Only the `leg-pipeline-designer` agent writes `legs/manifest.json`. All other agents and the Gradio app read it. This prevents concurrent write conflicts and keeps the manifest as a clean audit trail of what was added and when.
