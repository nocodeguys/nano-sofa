# EN-Props Schema — Polish UI / English JSON Contract

**Status:** Spec — do not implement until reviewed.
**Date:** 2026-05-11
**Scope:** `app-v2/data.jsx`, `app-v2/app-v2.jsx`, `app-v2/server.py`, `app/core/generator.py`

---

## 1. Problem statement

Three fields sent in the FormData POST — `lens`, `tod`, `shadow` — carry Polish display strings
all the way into the generation prompt. The server parses focal length out of `lens` by splitting
on `" mm"` and discards the intent descriptor (`"naturalna"` / `"produktowa"`). `tod` goes into
the `notes` blob verbatim in Polish. The JSON debug view in the Gradio stage mixes English `id`s
with Polish `name`s.

The fix is a clean layer boundary: **every prop that crosses the network boundary must be an
English stable `id`**. Polish strings live only in the `name` field of option-table objects in
`data.jsx` and are never sent to the server.

---

## 2. New option tables for `data.jsx`

Add these three tables alongside `COLORS`, `MATERIALS`, etc. They follow the existing `{id, name,
prop}` shape. Export them from `window.NS_DATA`.

```js
const LENSES = [
  { id: "35mm_wide",       name: "35 mm — reportażowy",  prop: "wide, documentary feel, slight distortion at edges" },
  { id: "50mm_natural",    name: "50 mm — naturalna",    prop: "natural perspective, matches human eye, general product" },
  { id: "85mm_product",    name: "85 mm — produktowa",   prop: "mild compression, flattering for furniture, catalog standard" },
  { id: "135mm_compress",  name: "135 mm — kompresja",   prop: "strong background compression, separates subject from backdrop" },
];

const TIMES_OF_DAY = [
  { id: "noon_neutral",    name: "południe — neutralne",  prop: "overhead neutral daylight, even color temperature ~5500 K, minimal shadows" },
  { id: "morning_warm",    name: "ranek — ciepłe",        prop: "low-angle warm morning light ~3200 K, long shadows, golden cast" },
  { id: "afternoon_soft",  name: "popołudnie — miękkie",  prop: "diffused afternoon light, slightly warm ~4500 K, medium shadows from one side" },
  { id: "overcast",        name: "zachmurzenie — studio", prop: "flat overcast light, no strong shadows, clean even illumination like studio strobe" },
  { id: "dusk_warm",       name: "zmierzch — ciepły",     prop: "low warm ambient ~2800 K, dramatic shadows, mood lighting" },
];

const SHADOWS = [
  { id: "soft_diffuse",    name: "miękkie rozproszone",   prop: "soft diffuse shadow, no strong directional cast, studio-box quality" },
  { id: "directional_4",   name: "kierunkowe — okno",     prop: "directional shadow falling at 4 o-clock, window light source" },
  { id: "hard_studio_5",   name: "twarde — studio",       prop: "hard shadow at 5 o-clock, studio strobe from upper right" },
  { id: "none",            name: "brak cienia",           prop: "no visible shadow beneath the product, floating isolation" },
];
```

**Update `window.NS_DATA` export:**

```js
window.NS_DATA = { COLORS, MATERIALS, SIZES_SOFA, SIZES_BED, CAMERAS, LEGS,
                   STEPS, ENVIRONMENTS, LENSES, TIMES_OF_DAY, SHADOWS };
```

**Default state values** (replace the current Polish string defaults in `useState`):

```js
// old
lens: "50 mm — naturalna", tod: "południe — neutralne", shadow: "miękkie rozproszone",

// new
lens: "50mm_natural", tod: "noon_neutral", shadow: "soft_diffuse",
```

---

## 3. JSON debug view and FormData — canonical English-only shape

### 3a. JSON debug view (`app-v2.jsx` lines 290–328)

The object that goes into the `pre` block and the clipboard copy must use English `id`s
throughout. Replace the current `scene` object shape:

```js
// current — BAD
scene: {
  environment: envObj?.id,       // "scandi"               — already English, keep
  camera: camObj?.id,            // "lounge"               — already English, keep
  lens: st.lens,                 // "85 mm — produktowa"   — Polish, must change
  time_of_day: st.tod,           // "południe — neutralne" — Polish, must change
  shadows: st.shadow,            // "miękkie rozproszone"  — Polish, must change
}

// new — all English ids
scene: {
  environment:  envObj?.id,                                  // "scandi"
  camera:       camObj?.id,                                  // "lounge"
  lens:         lensObj?.id   ?? st.lens,                   // "85mm_product"
  time_of_day:  todObj?.id    ?? st.tod,                    // "noon_neutral"
  shadows:      shadowObj?.id ?? st.shadow,                 // "soft_diffuse"
}
```

`lensObj`, `todObj`, `shadowObj` are computed the same way `camObj` and `envObj` are:

```js
const lensObj   = useMemo(() => LENSES.find(l => l.id === st.lens),         [st.lens]);
const todObj    = useMemo(() => TIMES_OF_DAY.find(t => t.id === st.tod),    [st.tod]);
const shadowObj = useMemo(() => SHADOWS.find(s => s.id === st.shadow),      [st.shadow]);
```

Also remove `name`, `label`, `lens` (the Polish-string version), and any Polish values from
the `variant` sub-object. Concretely:

```js
// current — keeps Polish name and dim
size: { id: sizeObj?.id, label: sizeObj?.name, dim: sizeObj?.dim },

// new — English id only; dim is acceptable since it's a measurement not natural language
size: { id: sizeObj?.id, dim: sizeObj?.dim },

// current — leaks Polish name
material: { id: matObj?.id, name: matObj?.name, notes: st.matNotes || null },

// new — English id and prop descriptor; name removed
material: { id: matObj?.id, prop: matObj?.prop, notes: st.matNotes || null },

// current — leaks Polish name and hex together
color: st.color === "custom"
  ? { custom: st.colorCustom }
  : { id: colorObj?.id, name: colorObj?.name, hex: colorObj?.hex },

// new — English id and hex; name removed (hex is machine-readable, not natural language)
color: st.color === "custom"
  ? { custom: st.colorCustom }
  : { id: colorObj?.id, hex: colorObj?.hex },
```

### 3b. FormData POST to `/api/generate` — field renames and changes

| Old field | Old value example | New field | New value example | Notes |
|---|---|---|---|---|
| `lens` | `"85 mm — produktowa"` | `lens` | `"85mm_product"` | Same field name, value changes to English id |
| `tod` | `"południe — neutralne"` | `tod` | `"noon_neutral"` | Same field name, value changes to English id |
| `shadow` | `"miękkie rozproszone"` | `shadow` | `"soft_diffuse"` | Same field name, value changes to English id |
| `res` | `"1K — Flash limit"` | `res` | `"1K"` | Strip the Polish suffix entirely at the source; server already does `res.split(" ")[0]` as a workaround but that workaround can be removed |
| `color` | `"saliw"` | `color` | `"saliw"` | Already an English id — no change |
| `mat` | `"boucle"` | `mat` | `"boucle"` | Already an English id — no change |
| `cam` | `"studio"` | `cam` | `"studio"` | Already an English id — no change |
| `env` | `"scandi"` | `env` | `"scandi"` | Already an English id — no change |

No fields are added or removed. Only the value types for `lens`, `tod`, `shadow` change.

---

## 4. Server-side mapping tables (`server.py`)

### 4a. Replace `lens` parsing with a lookup table

Current code (lines 256–258):
```python
try:
    focal_length_mm = int(lens.split(" mm")[0].strip())
except Exception:
    focal_length_mm = 50
```

This discards the intent descriptor entirely. Replace with:

```python
_LENS_TO_PROMPT = {
    "35mm_wide":      {"focal_mm": 35,  "descriptor": "35 mm wide-angle, slight perspective exaggeration, documentary feel"},
    "50mm_natural":   {"focal_mm": 50,  "descriptor": "50 mm natural perspective, standard catalog lens"},
    "85mm_product":   {"focal_mm": 85,  "descriptor": "85 mm short telephoto, mild background compression, product photography standard"},
    "135mm_compress": {"focal_mm": 135, "descriptor": "135 mm telephoto, strong background compression, subject isolated from backdrop"},
}
_LENS_DEFAULT = {"focal_mm": 50, "descriptor": "50 mm natural perspective, standard catalog lens"}
```

Usage in the endpoint:
```python
lens_data = _LENS_TO_PROMPT.get(lens, _LENS_DEFAULT)
focal_length_mm = lens_data["focal_mm"]
lens_descriptor = lens_data["descriptor"]   # passed into scene block, not notes
```

### 4b. New `tod` lookup table

Current code (lines 275–276) passes `tod` verbatim as Polish into notes:
```python
if tod:
    notes_parts.append(f"time of day: {tod}")   # "time of day: południe — neutralne"
```

Replace with:
```python
_TOD_TO_PROMPT = {
    "noon_neutral":   "midday neutral daylight, approximately 5500 K, overhead light with even short shadows",
    "morning_warm":   "early morning warm light, approximately 3200 K, low-angle golden cast, long shadows from the left",
    "afternoon_soft": "mid-afternoon diffused light, approximately 4500 K, gentle directional light from upper right",
    "overcast":       "flat overcast illumination, no directional shadows, even studio-strobe quality light",
    "dusk_warm":      "dusk warm ambient, approximately 2800 K, low-angle dramatic shadows, orange-red color cast",
}
```

The resolved string is injected **directly into the structured SCENE block** (see section 6),
not appended to `notes_parts`.

### 4c. New `shadow` lookup table

Replace the current `shadow_map` dict (lines 260–265):
```python
# current
shadow_map = {
    "miękkie rozproszone": "soft diffuse, no strong directional shadow",
    "kierunkowe — okno": "4 o-clock",
    "twarde — studio": "5 o-clock hard",
}
shadow_direction = shadow_map.get(shadow, "soft diffuse, no strong directional shadow")
```

Replace with:
```python
_SHADOW_TO_PROMPT = {
    "soft_diffuse":   {"direction": "soft diffuse",  "desc": "soft diffuse shadow, no strong directional cast, box-light quality"},
    "directional_4":  {"direction": "4 o-clock",     "desc": "directional shadow at 4 o-clock, window light from upper left"},
    "hard_studio_5":  {"direction": "5 o-clock",     "desc": "hard shadow at 5 o-clock, studio strobe from upper right"},
    "none":           {"direction": None,             "desc": "no shadow beneath the product"},
}
_SHADOW_DEFAULT = {"direction": "soft diffuse", "desc": "soft diffuse shadow, no strong directional cast"}
```

Usage:
```python
shadow_data  = _SHADOW_TO_PROMPT.get(shadow, _SHADOW_DEFAULT)
shadow_direction = shadow_data["direction"]   # existing field on GenerationRequest
shadow_desc      = shadow_data["desc"]        # new field, passed into scene block
```

### 4d. `_ENV_TO_SCENE` — mark packshot vs lifestyle environments

Add a `mode` classification to each entry. This drives the two-mode SCENE block in generator.py.
The simplest server-side structure is a tuple `(mode, description)` rather than a flat string:

```python
_ENV_TO_SCENE = {
    "studio_white":  ("packshot",   "clean white studio cyclorama, soft even lighting, e-commerce catalog"),
    "studio_grey":   ("packshot",   "neutral grey studio cyclorama, packshot lighting"),
    "transparent":   ("packshot",   "transparent background, isolated product, no environment"),
    "scandi":        ("lifestyle",  "scandinavian living room with light oak floors, white walls, indoor plants"),
    "loft":          ("lifestyle",  "industrial loft with exposed brick, concrete, and dark metal accents"),
    "japandi":       ("lifestyle",  "japandi interior, warm minimalist palette, natural wood, soft light"),
    "boho":          ("lifestyle",  "bohemian living room with rattan, woven textiles, warm earthy tones"),
    "dark_moody":    ("lifestyle",  "moody dark interior with deep walls and warm lamp lighting"),
    "garden":        ("lifestyle",  "outdoor terrace / garden setting with greenery and natural daylight"),
    "showroom":      ("lifestyle",  "brand showroom with subtle product staging, neutral palette"),
    "custom":        ("lifestyle",  "custom interior referenced by the user's uploaded background image"),
}
```

Usage:
```python
env_mode_label, env_scene_desc = _ENV_TO_SCENE.get(env, ("packshot", "neutral grey studio backdrop"))
```

---

## 5. `GenerationRequest` — two new fields

`app/core/generator.py` (the dataclass / TypedDict holding the request):

```python
# Add to GenerationRequest:
lens_descriptor:   str = ""    # English prompt fragment from _LENS_TO_PROMPT
tod_description:   str = ""    # English prompt fragment from _TOD_TO_PROMPT
shadow_description: str = ""   # English prompt fragment from _SHADOW_TO_PROMPT
env_mode:          str = "packshot"   # "packshot" | "lifestyle"
env_description:   str = ""    # English scene description from _ENV_TO_SCENE
```

The server endpoint populates these four fields when building `GenerationRequest`:

```python
req = GenerationRequest(
    ...
    focal_length_mm=focal_length_mm,
    lens_descriptor=lens_descriptor,
    tod_description=_TOD_TO_PROMPT.get(tod, ""),
    shadow_direction=shadow_data["direction"],
    shadow_description=shadow_data["desc"],
    env_mode=env_mode_label,
    env_description=env_scene_desc,
    notes="",   # notes_parts block removed; all fields go into structured SCENE block
    ...
)
```

The `notes_parts` assembly block (lines 274–304) that currently builds the `notes` string from
`tod`, `env_scene`, `env_note`, `env_mode`, and `seed` must be removed. `env_note` and `seed`
can remain in notes if the user supplied them, but `tod` and `env_scene` must not.

---

## 6. SCENE block rewrite for `generator.py`

### Current behavior (lines 295–305)

```python
if req.scene_reference_image is not None:
    lines.append(f"\nSCENE: Place the {product_noun} naturally within the scene ...")
else:
    lines.append("\nSCENE: Neutral studio backdrop. ...")
```

Problems:
1. When `scene_reference_image` is `None` but the user chose `loft` environment, the prompt
   contradicts the intent: it says "Neutral studio backdrop" while the `notes` tail says
   "environment: industrial loft with exposed brick". The model sees conflicting signals.
2. `tod`, `shadow`, and `lens` descriptors are buried in `ADDITIONAL NOTES` after the negative
   list — lowest-priority position in the prompt.
3. There is no structural distinction between a packshot (no environment context needed) and
   a lifestyle shot (environment is the primary creative instruction).

### Proposed replacement

Replace the `if req.scene_reference_image` block with a two-mode SCENE block. Insert it at the
same position in the prompt (after shadow direction, before preserve list).

```python
def _build_scene_block(req, product_noun: str) -> str:
    """
    Returns the full SCENE section for the prompt.
    Mode is determined by req.env_mode ('packshot' or 'lifestyle').
    Lens descriptor, time-of-day, and shadow description are woven into the
    scene paragraph rather than emitted as parallel name=value lines.
    """
    lens_clause = f" Lens: {req.lens_descriptor}." if req.lens_descriptor else ""
    shadow_clause = f" {req.shadow_description}." if req.shadow_description else ""

    if req.env_mode == "packshot":
        # Clean studio / isolated shot — environment detail is minimal.
        # time-of-day is translated into lighting temperature, not scene description.
        tod_clause = f" Lighting: {req.tod_description}." if req.tod_description else ""
        scene_desc = req.env_description or "neutral grey studio backdrop, packshot lighting"
        return (
            f"\nSCENE (packshot): {scene_desc}."
            f"{tod_clause}"
            f"{lens_clause}"
            f"{shadow_clause}"
            f" No environment objects, no room context — product only."
        )

    else:
        # Lifestyle shot — environment is the primary creative instruction.
        # Environment description goes first; lighting and lens follow as modifiers.
        tod_clause = f" Time of day / lighting quality: {req.tod_description}." if req.tod_description else ""
        scene_desc = req.env_description or "interior setting"
        if req.scene_reference_image is not None:
            placement = (
                f"Place the {product_noun} naturally within the scene shown in the "
                f"reference image. Match lighting direction, color temperature, and floor "
                f"material from the scene reference. "
            )
        else:
            placement = (
                f"Place the {product_noun} naturally within a {scene_desc}. "
                f"Render convincing room context — floor, walls, and ambient objects "
                f"consistent with the '{scene_desc}' description. "
            )
        return (
            f"\nSCENE (lifestyle): {placement}"
            f"{tod_clause}"
            f"{lens_clause}"
            f"{shadow_clause}"
            f" The shadow beneath the {product_noun} must fall in the same direction "
            f"as all other shadows in the scene."
        )
```

Call site in `_build_prompt_text` — replace lines 295–305:

```python
# old
if req.scene_reference_image is not None:
    lines.append(...)
else:
    lines.append(...)

# new
lines.append(_build_scene_block(req, product_noun))
```

This also makes the `ADDITIONAL NOTES` block narrower — it no longer receives `tod` or
`env_scene` fragments. Only genuine free-form operator notes remain there.

### Why environment description goes first in lifestyle mode

The model's attention weight is highest near the beginning of a section. Burying the environment
type in an `ADDITIONAL NOTES` tail means it competes with the negative list and output style for
attention. Moving it to `SCENE:` as a named section header anchors it as a primary instruction
at the same level as `UPHOLSTERY:` and `CAMERA:`. The contradiction with "Neutral studio
backdrop" is eliminated because the hardcoded fallback string is removed entirely.

---

## 7. Migration note — FormData diff

The changes touch only **value encoding**, not field names (except the `res` suffix removal):

| Field | Before | After | Server change |
|---|---|---|---|
| `lens` | Polish string `"85 mm — produktowa"` | English id `"85mm_product"` | Replace `split(" mm")` parser with `_LENS_TO_PROMPT` dict lookup |
| `tod` | Polish string `"południe — neutralne"` | English id `"noon_neutral"` | Replace verbatim `notes` append with `_TOD_TO_PROMPT` dict lookup → `tod_description` field |
| `shadow` | Polish string `"miękkie rozproszone"` | English id `"soft_diffuse"` | Replace `shadow_map` dict with `_SHADOW_TO_PROMPT` dict lookup; add `shadow_description` field |
| `res` | `"1K — Flash limit"` | `"1K"` | Remove `split(" ")[0]` workaround; accept clean token directly |
| All other fields | Unchanged | Unchanged | No change |

No new fields are added to the FormData. No existing fields are removed.

The server endpoint signature (`api_generate` in `server.py`) keeps the same parameter names
with `Form(...)` defaults updated to English ids:

```python
# old defaults
lens:   str = Form("50 mm — naturalna"),
tod:    str = Form("południe — neutralne"),
shadow: str = Form("miękkie rozproszone"),
res:    str = Form("1K — Flash limit"),

# new defaults
lens:   str = Form("50mm_natural"),
tod:    str = Form("noon_neutral"),
shadow: str = Form("soft_diffuse"),
res:    str = Form("1K"),
```

---

## 8. What the clean JSON contract looks like after all changes

```json
{
  "product": {
    "type": "sofa",
    "base": "sofa-katalog-2026.jpg"
  },
  "variant": {
    "color":    { "id": "graphi", "hex": "#3B3D3F" },
    "material": { "id": "velvet", "prop": "kierunkowy włos", "notes": null },
    "size":     { "id": "3",      "dim": "220x95 cm" },
    "legs":     "keep"
  },
  "scene": {
    "environment": "loft",
    "camera":      "lounge",
    "lens":        "85mm_product",
    "time_of_day": "afternoon_soft",
    "shadows":     "directional_4"
  },
  "references": [],
  "output": {
    "model":      "gemini-2.5-flash-image",
    "aspect":     "4:3",
    "resolution": "1K",
    "seed":       null
  }
}
```

Every value is either an English stable id, a hex color, a numeric measurement, or `null`.
No Polish strings cross the network boundary.

The model receives the scene as:

```
SCENE (lifestyle): Place the sofa naturally within a industrial loft with exposed brick,
concrete, and dark metal accents. Render convincing room context — floor, walls, and ambient
objects consistent with the 'industrial loft with exposed brick, concrete, and dark metal
accents' description. Time of day / lighting quality: mid-afternoon diffused light,
approximately 4500 K, gentle directional light from upper right. Lens: 85 mm short telephoto,
mild background compression, product photography standard. Directional shadow at 4 o-clock,
window light from upper left. The shadow beneath the sofa must fall in the same direction as
all other shadows in the scene.
```

This is purely English, structured, and free of the contradiction between the hardcoded
"Neutral studio backdrop" fallback and the user's chosen environment.

---

## 9. Coordination notes

- The `material.prop` field in `data.jsx` currently contains Polish text
  (`"kierunkowy włos"`, `"miękki, pętelkowy"`, etc.). Those values end up in the JSON debug
  view and should remain Polish-only UI-side strings. The server uses `_MATERIAL_PL_TO_EN`
  keyed on `id`, so `prop` never reaches the prompt. If the debug JSON must also be fully
  English, add an English `en_prop` field to each `MATERIALS` entry and reference that in
  the JSON view instead of `prop`.

- The `material.prop` in `CAMERAS` and `ENVIRONMENTS` is similarly Polish-only UI metadata.
  Those values are never sent to the server in any path today, so no change is required.

- `color_custom` (free-form text) can remain Polish or English — it is the user's own
  description and goes directly into the English prompt as a color descriptor. That path is
  already handled correctly by the server (`upholstery_color = color_custom.strip()`).
