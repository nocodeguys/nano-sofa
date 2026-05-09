# Sofa schema — test matrix

Used to evaluate `prompts/schemas/sofa.json`. Run after any schema edit. Current schema version: **0.2.0**.

---

## Base configuration for all evals

Unless a row states otherwise: 3-seater, neutral linen, tapered oak legs, `front-34-left` angle, `gemini-2.5-flash-image` model, `1K` resolution, studio scene (no scene reference). Shadow direction: `4 o-clock`. `leg_count`: 4.

Preserve list for all rows: `frame_geometry`, `cushion_count_and_arrangement`, `stitching_pattern`, `piping_and_seam_geometry`, `armrest_silhouette`, `seat_depth`, `overall_proportions`, `camera_angle`, `perspective`, `leg_count_and_positions`.

---

## Variant combinations (15 evals)

| # | Color | Material | Legs | Scene | Model | Resolution | Stress target |
|---|---|---|---|---|---|---|---|
| 1 | sage green | bouclé | tapered_walnut | studio | flash | 1K | Baseline: color + material + leg swap |
| 2 | charcoal | leather-aniline | plinth_oak | scandi-loft | flash | 1K | Leather rendering, dark color, scene ref (fills slot 3, no swatch) |
| 3 | terracotta | linen | hairpin_blacksteel | mid-century-living | flash | 1K | Thin metal legs, warm tone, multi-axis change |
| 4 | ivory | wool-blend | tapered_walnut | studio | flash | 1K | Light color, fabric texture |
| 5 | navy | performance-velvet | block_oak | studio | flash | 1K | Velvet sheen direction, heavy leg |
| 6 | rust | chenille | bun_walnut | rustic-living | flash | 1K | Tactile fabric + ornate leg + scene — all 3 ref slots used |
| 7 | sage green | bouclé | hairpin_blacksteel | studio | flash | 1K | Leg-only swap; isolates leg-geometry-morphing failure mode |
| 8 | sage green | bouclé | plinth_oak | studio | flash | 1K | Leg-only swap (block to plinth); isolates morphing |
| 9 | sage green | linen | tapered_walnut | studio | flash | 1K | Material-only swap; isolates fabric seam warping |
| 10 | sage green | leather-pigmented | tapered_walnut | studio | flash | 1K | Material-only swap, hard surface |
| 11 | sage green | bouclé | tapered_walnut | scandi-loft | flash | 1K | Scene-only swap; isolates shadow-direction inconsistency |
| 12 | sage green | bouclé | tapered_walnut | mid-century-living | flash | 1K | Scene-only swap |
| 13 | ivory | bouclé | tapered_walnut | studio | 3.1-flash-preview | 2K | Preview model, 2K output; validates resolution parameter behavior |
| 14 | sage green | bouclé | tapered_walnut | scandi-loft | 3.1-flash-preview | 2K | 4 ref slots: base + leg + scene + swatch; validates slot_4_swatch on preview model |
| 15 | charcoal | leather-aniline | hairpin_blacksteel | studio | flash | 1K | Alpha-bleed test: pass base photo with alpha channel present, `base_image_has_alpha: true`, verify app flattens to 18% grey before sending |

Rows 7–10 and 11–12 isolate single axes; useful for diagnosing which axis broke when a variant fails.

Row 15 is the only row that intentionally tests a pre-processing behavior rather than a generation output. Pass criterion is that the app sends a solid-background image to the model, not the raw alpha PNG.

---

## Pass/fail criteria per generation

For each output image, evaluate all of the following:

**Geometry preservation**
- Frame, cushion count, and armrest silhouette match the base reference. Proportional deviation must be within ~3% on any dimension.
- No decorative throw pillows, blankets, or accessories added that are not in the base reference.
- Cushion count is identical to base (neither added nor removed).

**Camera angle**
- Within 5° of the base reference angle. On `front-34-left` runs, the sofa must remain visibly left-facing at roughly 35°. Flag any output where the angle has drifted to something closer to `front-0` or `side-90`.

**Leg fidelity** (tests 1–8, 12–14)
- Leg style matches the manifest reference render. Proportions correct. Material and finish identifiable.
- Leg count matches `product.leg_count`. Fail if any leg is duplicated, missing, or partially merged with another.
- No braces, brackets, or spur elements not present in the leg reference.

**Shadow direction** (all tests with scene or leg swap: 2, 3, 5, 6, 7, 8, 11, 12, 14)
- Cast shadow falls in the direction stated in `camera.shadow_direction` (nominal: `4 o-clock`). Fail if shadow direction visibly contradicts the scene reference or the stated clock position.
- Leg contact shadows must be consistent with the main body shadow. This is the primary check for the shadow-direction-inconsistency failure mode.

**Fabric / material readability**
- The named material is identifiable at a glance. Bouclé loops must be visible. Leather grain must be visible. Velvet pile direction must read correctly relative to the camera.
- For materials with seams (bouclé, chenille, tufted cushions): piping and seam geometry must match base reference. No warp artifacts at piping lines or cushion edges.

**Color accuracy**
- Named color is perceptually correct under the reference lighting. Obvious failures (sage green rendering as olive, ivory rendering as pure white) count as fail. Evaluate with the scene reference as context for scene-placed renders.

**Scene integration** (rows 2, 3, 6, 11, 12, 14)
- Lighting direction in the generated image matches the scene reference.
- Floor contact shadow is plausible and direction-consistent.
- Product does not appear pasted-in; color temperature of the sofa fabric matches the ambient lighting in the scene.

**Text and label absence**
- No visible text anywhere in the output. No brand names, price tags, watermarks, or hallucinated labels. This is a hard fail regardless of image quality elsewhere.

**Alpha bleed** (row 15 only, pre-processing check)
- Verify at the network/request level (not the visual output level) that the image sent to the API has a solid grey background, not an alpha channel. A visual pass is necessary but not sufficient for this test.

**3-ref ceiling compliance** (row 6: flash model with base + leg + scene)
- Confirm via request log that exactly 3 image parts were sent. No 4th image part. If the request log shows 4 parts on a Flash model, this is a pipeline bug.

---

## Regression set

Three known-good generations to re-run after every schema change. Compare side-by-side against the prior saved output.

1. **Row 1** (sage bouclé / tapered walnut / studio / flash / 1K) — baseline color+material+leg swap. Simplest case; should be the most stable.
2. **Row 3** (terracotta linen / hairpin / mid-century / flash / 1K) — multi-axis change with thin metal legs and scene reference. The most failure-mode-dense single test.
3. **Row 7** (sage bouclé / hairpin / studio / flash / 1K) — leg-only swap. Isolates leg-geometry-morphing in regression.

If any regression output degrades on a dimension that the previous pass passed, do not merge the schema change until the cause is identified.

---

## Multi-turn drift test (run separately, not part of standard eval batch)

This is not a variant combination test. It validates the `multi_turn` block behavior.

1. Run row 1 (sage bouclé / tapered walnut / studio) as turn 1.
2. Pass the output image as the new base reference plus the thought signatures from turn 1. Change only the leg style to `hairpin_blacksteel`. Run as turn 2.
3. From the turn 2 output, change only the color to `charcoal`. Run as turn 3 with turn 2's thought signatures.
4. At turn 3, verify: stitching pattern matches original base, leg style matches turn 2's hairpin reference (not the walnut from turn 1), color is charcoal.
5. Run a turn 4 without resetting the chain (do not save intermediate). Change material to `leather-aniline`. This turn is expected to show identity drift. Document which attributes drifted and by how much.

Pass criterion for turns 1–3: all three preserve-list attributes remain within the geometry pass/fail thresholds above. Turn 4 is a failure-mode documentation exercise, not a pass/fail test.

---

## Logging

Each eval generation is tagged `eval=sofa-v0.2.0-N` in the library so they are filterable and do not pollute production output counts. The `N` is the row number from the table above. Multi-turn drift test generations are tagged `eval=sofa-v0.2.0-MT-N` where N is the turn number.
