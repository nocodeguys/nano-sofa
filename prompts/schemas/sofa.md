# Furniture schema — design rationale

**Schema:** `prompts/schemas/sofa.json` (filename retained for backwards compatibility — schema now covers both sofas and beds)
**Version:** 0.3.0

---

## Why these fields

### `model` is now an enum, not a free string

In v0.1.0, `model` was an unconstrained string. The research pass (2026-05-08) confirmed that `gemini-2.5-flash-image-preview` was shut down on January 15, 2026 and will return a 404 on any call. An unconstrained string field means that stale model IDs pass schema validation silently. The enum now limits the field to the three currently live IDs. The Gradio app should still gate on this, but the schema is the first line of defense.

### `model_constraints` block

A read-only block that documents the per-model capability limits directly in the schema. The Gradio app reads this to enforce resolution options and reference-slot counts at form-render time without reaching back to the research doc. Key values captured here:

- `gemini-2.5-flash-image`: max 3 reference images, max 1K output, no `resolution` parameter.
- Preview models: max 14 reference images, up to 4K output, `resolution` parameter supported in `ImageConfig`.

This block must not be overridden in generation requests.

### `reference_slots` — the 3-ref ceiling problem

The research identifies the 3-ref cap on `gemini-2.5-flash-image` as a named failure mode. In v0.1.0 there was no schema field tracking which references were being assembled, which meant the pipeline could silently send 4 images to a 3-ref model (base + leg + scene + swatch), causing the fourth to be dropped or the call to error.

`reference_slots` gives each slot a declared purpose and makes the conflict visible: if `slot_3_scene_or_swatch` and `slot_4_swatch` are both populated and the model is `gemini-2.5-flash-image`, the Gradio app should surface an error before the request is sent.

Slot order is intentional and must be preserved. The model uses positional context to interpret which image is which. Slot 1 is always the base product. Slot 2 is always the leg reference when legs are being swapped. Slot 3 is the first optional reference (scene or swatch). Slot 4 is only reachable on preview-tier models.

### `system_instruction`

Research confirmed system instruction support on all three active models. System instructions are the highest-leverage single mitigation for implicit product redesign: they establish a standing constraint that persists across every turn without needing to be restated in the main prompt text. The default value in the schema is ready to use verbatim. Override it for specialized shooting scenarios (e.g., lifestyle scene builds that intentionally allow accessory addition).

### `product.leg_count`

The leg-geometry-morphing failure mode is mitigated by stating exact leg count in the prompt. The research notes that the model adds, removes, or merges legs when count is not stated. This field is serialized into the prompt as "exactly N legs, one at each corner." Backends must substitute the `[leg_count]` placeholder in `variant.legs.instruction` with this value.

### `product.preserve` additions: `piping_and_seam_geometry` and `leg_count_and_positions`

v0.1.0 had a strong preserve list for cushion and frame attributes but was missing two items specifically called out in the research:

- `piping_and_seam_geometry` — fabric warping at seams is a distinct, named failure mode, most visible on tufted and welted seam styles. Adding it to the enum means callers can select it explicitly, and the app should include it by default for any upholstery that is not plain woven.
- `leg_count_and_positions` — complements the new `product.leg_count` field; makes the preserve signal appear in both the structured preserve list and the camera/leg sections of the assembled prompt for belt-and-suspenders coverage.

### `variant.upholstery.base_image_has_alpha`

The background-bleed failure mode occurs when a transparent-background PNG is passed as a reference image. The model reconstructs a random studio background from training priors rather than treating alpha as "no content." The fix is to flatten alpha to 18% neutral grey before passing. This field flags whether pre-processing is needed; the Gradio app acts on the flag. Schema owners should not rely on callers knowing to flatten alpha manually.

### `variant.legs.explicit_descriptor`

Provides a text description of the leg style alongside the reference image. The research states the dual text+image signal is the primary mitigation for leg-geometry-morphing — the model sometimes blends adjacent leg styles when only an image reference is provided. The descriptor should be specific: leg shape, material, finish, presence or absence of braces, and bracket count.

### `camera.shadow_direction`

The shadow-direction-inconsistency failure mode requires explicit prompt text stating the clock position of the cast shadow. The model does not automatically match shadow angle for swapped elements (legs, scene backgrounds). This field is required when `variant.legs.reference` or `variant.scene.reference` are present. The Gradio app should enforce this. Clock-position notation ("4 o-clock") was chosen because it is unambiguous and matches the language used in the philschmid.de product photography guide referenced in the research.

### `camera.angle_degrees_from_left`

Numerical equivalent of the angle enum. The research notes that camera angle drift in long batches is mitigated by stating the angle numerically in the prompt (e.g. "three-quarter front view, approximately 35 degrees from the left") in addition to re-attaching the base reference. This field provides that number without requiring each caller to manually map enum values to degrees.

### `output.resolution` — corrected default and ceiling

v0.1.0 defaulted `resolution` to `"2K"` and the rationale doc said "current Nano Banana max output." Both were wrong for `gemini-2.5-flash-image`, which has a hard cap of 1K (1024px). The 2K and 4K options are only available on `gemini-3.1-flash-image-preview` and `gemini-3-pro-image-preview` via the `resolution` key in `ImageConfig`. The default is corrected to `"1K"`. The Gradio app must enforce the per-model ceiling using the `model_constraints` block.

### `negative` list — expanded

Three categories were added:

1. Text-related items split into explicit sub-types (`watermarks`, `brand labels`, `price tags`, `hallucinated text of any kind`) because the research calls out the text hallucination failure mode specifically for reference images containing visible labels. The previous single entry `"text"` was ambiguous about whether it covered hallucinated text vs. rendered text in the scene.
2. `throw pillows not present in reference` and `decorative accessories not present in reference` — the implicit redesign failure mode specifically mentions the model adding throw pillows unprompted. These are now explicit negative items.
3. `alpha channel artefacts` and `incorrect background reconstruction` — both arising from the transparent-background input failure mode.
4. `shadow direction inconsistent with scene lighting` — reinforces the shadow mitigation at the negative-list level.

### `multi_turn` block

The research identifies identity drift in multi-turn edits as a current, active failure mode (reported 2026-05 across multiple community sources). Fine features (stitching, leg joinery) drift between turns even when the original reference is re-attached. The mitigations are: (1) pass thought signatures from the prior turn back into the next request, and (2) limit chains to 2-3 turns from a single original, then re-anchor to a saved intermediate output.

The `multi_turn` block gives the Gradio app a place to track turn number and surface the chain-reset recommendation. `prior_thought_signatures` is an array because a single response can return multiple thought_signature parts.

### `product.preserve` remains mandatory and non-empty

No change from v0.1.0. This constraint stands as the primary defense against implicit redesign.

### `variant.legs.reference` is an ID, not a path

No change from v0.1.0.

### Camera angle is explicit even though it is "preserved"

No change from v0.1.0. Belt-and-suspenders confirmed necessary by the research (camera angle drift in long batches).

### Material enum is closed, color is open

No change from v0.1.0.

---

## Pricing notes (as of 2026-05-08)

- `gemini-2.5-flash-image`: $0.039/img standard, $0.0195/img batch. Input image cost is ~$0.000077/ref after the November 2025 token reduction (258 tokens at $0.30/1M). Three ref images add approximately $0.00023 per call — negligible.
- `gemini-3.1-flash-image-preview`: $0.067/img at 1K, $0.101/img at 2K, $0.151/img at 4K standard. Thinking overhead adds latency and tokens on complex multi-reference prompts.
- `gemini-3-pro-image-preview`: $0.134/img at 1K-2K, $0.240/img at 4K standard. Thinking tokens cannot be disabled and add $0.002-$0.006 per call plus 5-15% for complex prompts. Also: thinking tokens are billed even on failed safety-check generations — budget for this in high-volume runs.

---

## Test matrix

See `prompts/test-matrices/sofa.md` for the eval set and pass/fail criteria.

---

## Changelog

- **0.1.0** (initial) — first scaffold. Five canonical camera angles aligned with the leg library's render presets.
- **0.3.0** (2026-05-08) — bed support added. `product.type` is now `enum: ["sofa", "bed"]` instead of `const: "sofa"`. New optional `product.frame_style` field for bed-frame silhouettes (platform, panel, sleigh, four-poster, canopy, divan, ottoman-storage, captain, upholstered variants). `product.configuration` enum extended with bed sizes (twin/full/queen/king/california-king/european-*/super-king); the application layer is responsible for filtering to type-appropriate values. `product.leg_count` minimum lowered from 2 to 0 — platform beds have no visible legs, and the prompt builder now OMITS leg-count emphasis entirely when leg_count is 0 (the proximate cause of "model adds legs to bed photos"). `product.preserve` enum extended with bed-anatomy items (headboard_silhouette, headboard_height, footboard_geometry, footboard_presence, frame_silhouette, post_geometry, mattress_height, slat_visibility). Filename `sofa.json` retained — splitting into per-type files is a follow-up for furniture-prompt-architect (see `prompts/change-requests/`).
- **0.2.1** (2026-05-08) — leg swap is now explicitly optional. `variant.required` no longer includes `"legs"`, and inside `legs` the `reference` and `instruction` fields are no longer required. Omit the `legs` object entirely to preserve the existing legs from the base photo. The Gradio app already defaulted leg dropdown to "None — keep existing legs"; the schema is now consistent with that UI behavior. No breaking change for callers that did include legs.
- **0.2.0** (2026-05-08) — research-driven revision. Changes: (1) `model` field converted from free string to enum of three live model IDs; dead `gemini-2.5-flash-image-preview` ID no longer passes validation. (2) Added `model_constraints` block documenting per-model ref limits and resolution caps. (3) Added `reference_slots` to make the 3-ref ceiling explicit and prevent silent 4th-slot drops on Flash. (4) Added `system_instruction` field with default persona text as primary implicit-redesign mitigation. (5) Added `product.leg_count` for leg-geometry-morphing mitigation. (6) Added `piping_and_seam_geometry` and `leg_count_and_positions` to `preserve` enum. (7) Added `variant.upholstery.base_image_has_alpha` flag for background-bleed pre-processing. (8) Added `variant.legs.explicit_descriptor` for dual text+image leg signal. (9) Added `camera.shadow_direction` for shadow-inconsistency mitigation. (10) Added `camera.angle_degrees_from_left` for numeric angle in batch prompts. (11) Corrected `output.resolution` default from `"2K"` to `"1K"` (Flash stable is capped at 1K); added `"4K"` to enum for preview models. (12) Expanded `negative` defaults with text hallucination, throw-pillow, alpha-bleed, and shadow-direction entries. (13) Added `multi_turn` block for thought-signature passthrough and chain-reset signaling.
