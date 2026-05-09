# Adding a new leg style to the library

For non-technical teammates. You will need Blender (free, blender.org) and a text editor. The render step uses Docker so you do not need Blender installed locally if Docker is available.

---

## 1. Decide the style and material slug

Choose a short, lowercase, one-word slug for the style. No hyphens, no spaces.

Current styles in the library: `tapered`, `hairpin`, `plinth`, `bun`, `block`, `splayedtaper`, `turned`, `cabriole`, `squaretaper`.

New style slug examples: `bracket`, `sabre`, `x-base` (written as `xbase`), `cone`, `fluted`.

If you are adding a new material for an existing style (e.g., oak hairpin legs when only black steel and brass exist), your style slug stays the same — you are just adding another material render.

---

## 2. Source the 3D model

Where to look, in order of preference:

1. **Procedural (Blender only, no download)** — most leg styles can be built in Blender in under 30 minutes using the spin/lathe modifier (for round turned legs), a curve with a taper object (for tapered legs), or simple cube mesh edits (for block and plinth styles). This is the preferred route: zero license questions, you control the exact geometry.

2. **BlenderKit** (in-Blender add-on, blenderkit.com) — free tier includes furniture parts. Search "sofa leg", "table leg", "furniture foot". Note the asset ID from the BlenderKit panel — paste it into the manifest as the source.

3. **Poly Haven** (polyhaven.com) — CC0 license, smaller selection but high quality. Download as `.blend` or `.fbx`.

4. **Sketchfab** — filter "Downloadable" and "CC license". Always verify the specific CC licence (CC0 and CC-BY are fine; CC-NC or CC-ND are not acceptable for this library). Note the URL.

5. **AI image-to-3D** (Tripo, Meshy, or similar) — take a clean photo of a physical leg on a plain background, generate a 3D model, clean up in Blender. License is typically yours to use; note the tool used as the source.

Whatever source you use, **record the URL (or "procedural") and license** — both are required manifest fields.

---

## 3. Open the template blend file

Open `legs/source/_template.blend` in Blender. This file contains:

- Standard world settings (background colour, no HDRI).
- An empty object at the world origin named `LEG_REPLACE_ME` as a placement guide.

Do not touch the world settings. The render script adds lighting and the background plane — the .blend should not contain either.

---

## 4. Import or build the leg geometry

**If importing from a downloaded file:**

`File > Import` — pick the right importer for your file type (`.fbx`, `.obj`, `.glb`, `.stl`).

**If building procedurally:**

Use the spin modifier (for round turned shapes), curve modifier, or direct mesh editing. The geometry should be a single object.

After import or creation:

1. Rename the object to `LEG_<style>` (e.g., `LEG_hairpin`, `LEG_tapered`).
2. Move the leg so the **base of the leg — where it contacts the floor — sits exactly at the world origin (0, 0, 0).** To do this precisely: place the 3D cursor at the base of the leg, then Object menu > Set Origin > Origin to 3D Cursor.
3. Scale the leg to **12 cm tall** (the reference height). Check the exact height in the right sidebar (press N to toggle). If making a non-standard-height variant (e.g., a plinth at 8 cm or hairpins at 15 cm), scale to that height and you will set `geometry.default_height_cm` accordingly in the manifest.
4. Apply all transforms: Object menu > Apply > All Transforms.

---

## 5. Check the geometry

Confirm before saving:

- The pivot (orange dot) is at the base of the leg, not the centre.
- The leg height reads correctly in the N panel (Dimensions Y or Z depending on orientation).
- No lights in the scene.
- No floor or background plane — the render script provides these.
- Object is named `LEG_<style>`.

---

## 6. Save as the style's blend file

`File > Save As` → `legs/source/<style>.blend`

Use only the style slug, not the material slug — one .blend file serves all materials for a style.

---

## 7. Run the render script

From the project root in Terminal:

```
docker compose run --rm renderer <style>
```

This invokes:

```
blender --background legs/source/<style>.blend \
        --python legs/render-blender.py \
        -- <style>
```

The script produces all 5 angles × 7 materials = 35 main PNGs, 35 alpha PNGs, and 35 EXR source files. Total runtime is approximately 4-8 minutes per style depending on your hardware.

To render only specific materials or angles during development:

```
docker compose run --rm renderer <style> --materials walnut oak --angles front34l front34r
```

Check the output in `legs/` — filenames follow the pattern `<style>_<material>_<angle>.png`.

---

## 8. Write the manifest entries

Open `legs/manifest.json` in any text editor. For each material you rendered, add one entry. Copy an existing entry and fill in every field:

```json
"<style>_<material>": {
  "id": "<style>_<material>",
  "style": "<style>",
  "material": "<human-readable description, e.g. solid walnut, satin finish>",
  "material_slug": "<slug, e.g. walnut>",
  "explicit_descriptor": "<REQUIRED: see below>",
  "geometry": {
    "profile": "<free text shape description>",
    "default_height_cm": 12,
    "<any other relevant dimensions>": "<value>",
    "has_braces": false,
    "has_brackets": false,
    "has_stretchers": false,
    "attachment": "<threaded insert / welded plate / etc>"
  },
  "angles_available": ["front0", "front34l", "front34r", "side90", "low34"],
  "renders": {},
  "tags": ["<tag1>", "<tag2>"],
  "shadow_direction_hint": "4 o-clock",
  "source": "<source description or URL>",
  "source_url": "<URL or null>",
  "license": "CC0",
  "added": "<YYYY-MM-DD>",
  "added_by": "<your name or handle>"
}
```

### Writing the explicit_descriptor — the most important field

The `explicit_descriptor` is a short text description of the leg that gets sent to the generation model alongside the reference image. It is the primary defence against the leg-geometry-morphing failure mode (where the model blends adjacent leg styles instead of replacing cleanly).

**A good descriptor:**

- States the count ("four legs" — though the count is also in `product.leg_count`, belt-and-suspenders repetition helps).
- Names the exact shape ("tapered cylindrical", "three-rod hairpin", "S-curve cabriole with pad foot").
- Names the material and finish explicitly ("solid walnut with satin finish", "black powder-coated steel").
- States what is absent ("no braces, no brackets, no stretchers") — this prevents the model from hallucinating structural elements.
- Describes a distinguishing visual detail ("legs taper from 4 cm at the top to 2 cm at the base", "three parallel 8 mm rods bent into a hairpin shape").

**Bad descriptor:** "wooden tapered legs" — too vague; the model blends styles.
**Good descriptor:** "four tapered cylindrical legs, no braces, no brackets, no stretchers, solid walnut with a satin finish, grain running vertically, legs taper from approximately 4 cm diameter at the top to 2 cm at the base, dark chocolate brown"

Look at existing entries in `manifest.json` for reference.

### The renders object

After the render script runs successfully it updates the `"renders"` object automatically. If you added the manifest entry before rendering, the renders object starts empty (`{}`). After rendering, the script fills it in:

```json
"renders": {
  "front0":  { "main": "legs/<style>_<material>_front0.png",  "alpha": "legs/<style>_<material>_front0_alpha.png" },
  "front34l": { "main": "legs/<style>_<material>_front34l.png", "alpha": "legs/<style>_<material>_front34l_alpha.png" },
  "front34r": { "main": "legs/<style>_<material>_front34r.png", "alpha": "legs/<style>_<material>_front34r_alpha.png" },
  "side90":  { "main": "legs/<style>_<material>_side90.png",  "alpha": "legs/<style>_<material>_side90_alpha.png" },
  "low34":   { "main": "legs/<style>_<material>_low34.png",   "alpha": "legs/<style>_<material>_low34_alpha.png" }
}
```

If the automatic update did not run, fill this in by hand following the pattern above.

---

## 9. Verify the renders look right

Open each of the five angle PNGs for each material and check:

- The leg is fully visible, not clipped by the camera frame.
- The leg sits on the ground plane (not floating).
- The shadow is soft and falls rear-right (approximately 4-5 o-clock direction).
- The material looks right — wood materials should show some surface warmth; metal materials should show appropriate reflectivity.
- The background is neutral grey, not white or black.

Common issues:

| Symptom | Cause | Fix |
|---|---|---|
| Leg too big or clipped | Height is not 12 cm | Rescale in Blender, re-render |
| Leg floating above floor | Pivot is not at the base | Set origin to 3D cursor placed at the base, re-render |
| Wrong material colour | Imported material not overridden | The render script assigns materials by name; ensure the leg object has at least one material slot |
| Flat / no shadow | Lights missing from scene | The script adds lights — check that the script ran without errors |

---

## 10. Refresh the Gradio app

In your browser, reload the Gradio app. The leg picker reads `legs/manifest.json` on startup. Your new leg style appears in the picker with all its materials.

---

## Note on asymmetric leg styles

If your leg looks significantly different from the `front34l` versus `front34r` angle (e.g., a cabriole leg where each leg faces outward, or a sabre leg that is inherently directional), add a `_note_asymmetry` field to the manifest entry explaining this. When writing generation prompts for these legs, always include both front-quarter angles in the renders.
