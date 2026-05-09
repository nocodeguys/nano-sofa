# Leg reference library — standards

These rules are non-negotiable. Consistency across the library is what makes leg-swap quality reliable. Every render must pass every rule below before its manifest entry is marked ready.

---

## Geometry

- **Pivot at base contact point.** The point where the leg meets the floor is the world origin (0, 0, 0). No exceptions. This makes scaling and shadow alignment trivial in downstream compositing, and ensures the sofa schema `camera.shadow_direction` field corresponds correctly to the rendered shadow.
- **Reference height: 12 cm.** All legs render at this height by default. Shorter or taller versions of the same style are separate manifest entries with `geometry.default_height_cm` set explicitly.
- **Real-world scale.** Modelled at 1:1 cm in Blender. The camera rig in `render-blender.py` is calibrated for 12 cm objects — deviate from the height spec and the leg will be clipped or will appear toy-sized.
- **No geometry beyond the leg itself.** Do not include a sofa base, mounting hardware, or floor surface in the leg mesh. The background plane is added by the render script.

---

## Lighting

Identical 3-point softbox rig applied to every leg in the library. Do not modify this setup when rendering. The script `legs/render-blender.py` builds it programmatically — changes to lighting must be made in the script, not in the .blend file directly, so they apply to the whole library uniformly.

| Light | Position | Type | Size | Intensity | Colour |
|---|---|---|---|---|---|
| Key | Upper-front-left | Area | 1.5 × 1.5 m at 4 m distance | 800 W | 5500 K |
| Fill | Upper-right | Area | 1.0 × 1.0 m at 3 m distance | 240 W (30% of key) | 5500 K |
| Rim | Rear | Area | 0.8 × 0.8 m at 2.5 m distance | 400 W | 5500 K |

No HDRI environment. Pure 3-point setup produces a single, soft, predictable contact shadow that the model can match when shadow_direction is stated in the generation prompt.

**Shadow direction from this rig:** The primary contact shadow falls rear-right from the leg, approximately at the 4-5 o-clock position. This maps to `"shadow_direction": "4 o-clock"` in `prompts/schemas/sofa.json`. When using any leg from this library in a generation request, set `camera.shadow_direction` to `"4 o-clock"` unless you have overridden the lighting rig.

---

## Background

- 18% neutral grey plane — sRGB value `#7F7F7F`, linear value ~0.2159.
- This matches the `variant.upholstery.base_image_has_alpha` pre-processing target in the sofa schema: base product images with alpha are flattened to the same 18% grey before generation, so leg references and base product images share the same background value. Consistent backgrounds eliminate the background-bleed failure mode when both images are passed as references.
- Single soft contact shadow under the leg, rendered into the main PNG.

---

## Output format

Two PNGs per leg per angle, named deterministically:

| File | Content | Alpha channel |
|---|---|---|
| `<style>_<material>_<angle>.png` | Leg + contact shadow on 18% grey | No (fully opaque) |
| `<style>_<material>_<angle>_alpha.png` | Leg only on transparent background | Yes |

Resolution: **1024 × 1024 px**, sRGB, 8-bit PNG.

Source EXR (16-bit DWAA compressed) retained at `legs/source/renders/<style>_<material>_<angle>.exr` for re-grading.

Rationale for 1024 px: matches `gemini-2.5-flash-image` max output resolution (1024 px) and the Flash model's 3-ref cap means the leg reference competes for one of only three slots. A 1024 px reference image costs approximately 258 input tokens on Flash (~$0.000077 per call). There is no quality benefit to sending larger reference images to this model; for preview-tier models that support 4K output, a 1024 px reference is upsampled internally.

---

## Canonical camera angles

Five renders per leg style. The angle slugs here map directly to the `camera.angle` enum in `prompts/schemas/sofa.json` (with hyphens replaced by nothing: `front-34-left` → `front34l`).

| Slug | Schema angle | Description |
|---|---|---|
| `front0` | `front-0` | Camera dead-on, leg axis perpendicular to camera |
| `front34l` | `front-34-left` | Camera 34° to the left of front (shows the right face of a corner leg) |
| `front34r` | `front-34-right` | Camera 34° to the right of front (shows the left face of a corner leg) |
| `side90` | `side-90` | Pure side profile |
| `low34` | `low-34` | Camera lowered, 34° upward tilt, three-quarter framing — matches low-angle lifestyle photography |

Always render the full set of five angles when adding a new leg. Skipping angles that seem redundant creates pipeline gaps when the Gradio app tries to angle-match a generation request.

---

## Materials baseline

For every leg style, render the full five-angle set in all seven materials:

| Slug | Label | Notes |
|---|---|---|
| `oak` | Solid oak, natural finish | Warm honey-blonde, moderate roughness |
| `walnut` | Solid walnut, satin finish | Dark chocolate brown, slight specular |
| `blacksteel` | Black powder-coated steel | Matte black, non-metallic (powder coat) |
| `brass` | Brushed brass | Metallic, anisotropic highlight from brushing |
| `chrome` | Polished chrome | Metallic, near-zero roughness, mirror-like |
| `mattewhite` | Matte white | High roughness, low specular |
| `whiteplastic` | Neutral white plastic (shape reference) | Used when only the geometry is the signal |

Total renders per leg style: 5 angles × 7 materials = 35 main PNGs + 35 alpha PNGs + 35 EXR source = 105 files per style.

---

## Naming convention

```
<style>_<material>_<angle>.png
```

Slugs are lowercase, no hyphens within a slug. Each part is a single token.

Examples:
- `tapered_walnut_front34l.png`
- `hairpin_blacksteel_side90.png`
- `plinth_oak_low34.png`
- `splayedtaper_brass_front34r.png`

The manifest ID for each leg is `<style>_<material>` (no angle — the angle is resolved at request time by the Gradio app using the `camera.angle` field from the generation request).

---

## Source files

Original `.blend` files live at `legs/source/<style>.blend`. They must contain:

- The leg geometry object, named `LEG_<style>` (e.g., `LEG_tapered`).
- Pivot at world origin (0, 0, 0). The leg base touches the floor at origin.
- No lights. The render script builds the standard lighting rig on each run.
- No background plane. The render script adds the grey backdrop.
- Material slots wired to placeholder materials. The render script swaps in the standard material parameterisations from the `MATERIALS` dict in `render-blender.py`.

Re-running `legs/render-blender.py <style>` against any `.blend` produces the full canonical render set deterministically (same samples, same seed, same camera matrices, same lighting positions).

---

## Asymmetric geometry note

Some leg styles look significantly different from the two front-quarter angles (e.g., cabriole legs, which are directional; splay legs, where the outward angle is most visible from the 34° positions). For such legs:

- Note the asymmetry in the manifest entry under `_note_asymmetry`.
- Always include both `front34l` and `front34r` in any generation prompt that uses these legs.
- The `explicit_descriptor` text in the manifest should mention the asymmetry so the model understands what to expect from the reference image.

---

## Gemini reference image optimisation notes

These notes are specific to how these renders are consumed by the Nano Banana generation pipeline.

1. **Background matches the base product pre-processing target.** The 18% grey background is the same value used when flattening transparent-background base product images (see `variant.upholstery.base_image_has_alpha` in the schema). This consistency reduces cross-image background discrepancy, which is a named cause of the background-bleed failure mode.

2. **Single leg per reference image.** Each render file shows exactly one leg instance. The `explicit_descriptor` text specifies the count (e.g., "four tapered cylindrical legs"). The model extrapolates count and placement from the text; the image provides the geometry signal. Do not render a group of four legs in the reference image — this was tested and produced worse geometry-morphing results than a single-leg reference plus explicit count in text.

3. **No labels, no text, no branding in renders.** The generation pipeline's negative list includes `"hallucinated text of any kind"`. Any text visible in a reference image is likely to be distorted or replaced. Keep renders clean.

4. **Shadow direction is the canonical "4 o-clock"** for all legs rendered under the standard rig. Downstream users: always set `camera.shadow_direction` to `"4 o-clock"` when using any leg from this library, unless the sofa base product photo has a shadow that clearly differs, in which case re-render the leg reference with a modified lighting rig and document the shadow direction used.

5. **Alpha PNG for compositing.** The `_alpha.png` variant is not sent to the generation model directly. It is available for manual compositing workflows (e.g., pre-compositing a leg reference into a scene image before passing it to the model). Do not pass transparent PNGs directly to any Nano Banana model — transparent background input is unsupported and triggers the background-bleed failure mode.
