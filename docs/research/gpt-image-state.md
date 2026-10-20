# OpenAI GPT Image — State as of 2026-10-20

Companion to `nano-banana-state.md`. Same spirit: what is true today about the
OpenAI image models we call from `app-v2/studio/openai_images.py`, what the
official docs actually say about prompting, what practitioners report for
product / furniture / fabric work, and where our implementation drifts from
the official guidance.

Every finding is tagged **[OFFICIAL]** (OpenAI docs, API reference, cookbook,
changelog, launch post) or **[COMMUNITY]** (practitioner write-ups, vendor
blogs, forum threads). Vendor-hosted guides (fal, Atlas Cloud, Tosea, Pixmax,
Fuser…) are community, even when they quote OpenAI.

---

## ⚠ Implications for current architecture

1. **The model ids and 16-reference cap are correct.** `gpt-image-2.5-flare`
   and `gpt-image-2.5-sunburst` (snapshots `-2026-09-08`) are the current
   line-up and the recommended migration target for every older GPT Image
   model. `/v1/images/edits` takes up to 16 images per call. **[OFFICIAL]**

2. **`input_fidelity` is dead for everything we call directly.** It exists
   only on `gpt-image-1` / `gpt-image-1.5` (`low`|`high`, default `low`) and
   `gpt-image-1-mini` (`low` only). `gpt-image-2` and both 2.5 models reject it
   with HTTP 400 `invalid_input_fidelity_model` — "The model '…' does not
   support the 'input_fidelity' parameter" — because every image input is
   processed at high fidelity automatically. Our `input_fidelity: False` flag
   and the retry-without-it path are correct; the docstring and the
   ARCHITECTURE.md sentence that still say "with `input_fidelity: high`" are
   stale. **[OFFICIAL]**

3. **The quality ladder moved under our feet.** On 2.5, `high` spends the
   output-token budget that `gpt-image-2` spent on `medium` (1,413 tokens at
   2048×1152); 2.5 `max` ≈ `gpt-image-2` `high` (5,650). Our
   `default_quality: "high"` therefore renders at what used to be "medium"
   detail. For fabric macro fidelity the realistic tiers are `xhigh` / `max`.
   **[COMMUNITY, measured: Tosea 41-call benchmark; Pixmax]**

4. **Our price hint is wrong at the top of the ladder.** "≈$0.01–0.13/obraz
   przy 1K" matches `low`→`high`; `max` at 1024×1024 lands near the old
   `gpt-image-2 high` price (~$0.21/image), and at 3840×2160 `max` is ~$0.40.
   The per-token rates in `_GPT_IMAGE_2_RATES` are still right ($5 / $8 / $30
   per 1M). **[OFFICIAL rates; COMMUNITY per-image figures]**

5. **Three of our 2K sizes are in OpenAI's "experimental" zone.** Custom sizes
   are valid when both edges are multiples of 16, the ratio is within 1:3–3:1,
   no edge exceeds 3840 and total pixels are 655,360–8,294,400 — every row in
   `_ASPECT_SIZES_1K` passes, at 1K and 2K. But "resolutions above 2560×1440
   are experimental", i.e. above 3,686,400 px, which our 2K rows for 3:4
   (1728×2304), 4:3 (2304×1728) and 21:9 (3024×1296) exceed. They work, but
   OpenAI does not vouch for them. **[OFFICIAL]**

6. **Every maskless edit regenerates the whole canvas.** Masks exist but are
   "entirely prompt-based" guidance — the model "may not follow its exact
   shape with complete precision" — and apply to the first image only. Our
   fabric / colour swaps are full re-renders, so backdrop, framing and the
   product's silhouette are all up for renegotiation every call. The official
   remedy for pixel-exact regions is to composite the approved edit back into
   the original yourself. **[OFFICIAL]**

7. **No seed, no determinism.** Neither `/v1/images/generations` nor
   `/v1/images/edits` documents a `seed`; OpenAI lists "consistency across
   generations" as a known limitation. Consistent sets come from re-feeding
   the accepted output as `image[1]` plus a repeated preserve list, not from
   the API. **[OFFICIAL]**

8. **Deprecation clock on the OpenRouter fallbacks.** `gpt-image-1` shuts
   down **2026-10-23** (three days from this note); `gpt-image-1-mini` and
   `gpt-image-1.5` on **2026-12-01**. `studio/openrouter.py` still lists
   `openai/gpt-image-1` and `openai/gpt-image-1-mini`. **[OFFICIAL]**

9. **`quality: auto` is unpredictable — keep setting it explicitly.** Both
   2.5 models default to `auto`; one benchmark saw auto land on a 628-token
   budget never produced by any explicit tier. We already send the tier
   explicitly; keep it that way. **[OFFICIAL default; COMMUNITY variance]**

10. **The texture-smoothing complaint is real and unsolved by prompting.** A
    catalogue editor reported on 2026-09-03 that `gpt-image-2` product edits
    produce "plastic", over-smoothed skin across thousands of generations and
    that "strong product-lock instructions and repeated constraints do not
    reliably solve it"; OpenAI Support only passed it on (2026-09-10). Curious
    Refuge saw the same fractal / over-sharpened surface texture on 2.5
    Sunburst at 4K. Expect the same on fabric pile. **[COMMUNITY]**

---

## Model line-up (2026-10-20)

| API model id | Role | Snapshot | Edits refs | Quality tiers | Sizes | Status |
|---|---|---|---|---|---|---|
| `gpt-image-2.5-flare` | "fastest model for high-quality, everyday image generation"; small model, speed-optimised, quality "comparable to GPT Image 2" | `gpt-image-2.5-flare-2026-09-08` | 16 | `low` `medium` `high` `xhigh` `max` `auto` | 3 standard + custom | Current, recommended default |
| `gpt-image-2.5-sunburst` | base model, quality-optimised, "higher image quality than GPT Image 2", "for workflows where editing precision matters most", longer generation | `gpt-image-2.5-sunburst-2026-09-08` | 16 | same | same | Current, premium |
| `gpt-image-2` | April 2026 model; "flexible image sizes, high-fidelity image inputs, token-based pricing" | `gpt-image-2-2026-04-21` | 16 | `low` `medium` `high` `auto` | 3 standard + custom | Current, not deprecated; transparency "in preview" |
| `gpt-image-1.5` | Dec 2025 | — | 16 | `low` `medium` `high` | 3 standard only | **Shutdown 2026-12-01** |
| `gpt-image-1-mini` | Oct 2025 | — | 16 | `low` `medium` `high` | 3 standard only | **Shutdown 2026-12-01** |
| `gpt-image-1` | Apr 2025 | — | 16 | `low` `medium` `high` | 3 standard only | **Shutdown 2026-10-23** |
| `chatgpt-image-latest` | alias of whatever ChatGPT runs | — | — | — | — | moving target, avoid in pipelines |
| `dall-e-2` / `dall-e-3` | — | — | — | — | — | **Removed 2026-05-12** |

Sources: model pages, API reference (`images.edit` / `images.generate`),
deprecations page, changelog (2026-04-21, 2026-08-20, 2026-09-08), image
prompting guide. **[OFFICIAL]**

Notes:

- A bare `gpt-image-2.5` id does not exist (model-not-found). **[COMMUNITY,
  consistent across sources]**
- Endpoints for all 2.5 models: `v1/images/generations`, `v1/images/edits`,
  `v1/batch`. The model pages list Batch as supported with $15/M output; one
  news write-up (datanorth) says Batch is *not* supported on 2.5 — the model
  page is the authority, but verify before relying on batch pricing.
  **[OFFICIAL vs COMMUNITY conflict]**
- The Responses API image tool is a separate path (`gpt-5`+ mainline model
  with an image tool); cached-input pricing applies **only** there, never to
  direct `/v1/images/*` calls. **[OFFICIAL]**
- `/v1/images/edits` accepts `application/json` (base64 images) since
  2026-02-09, in addition to multipart. **[OFFICIAL]**
- Organisation verification may be required to use GPT Image models.
  **[OFFICIAL]**

### Rate limits (default, per model page)

| Tier | TPM | IPM |
|---|---|---|
| Build | 250,000 | 20 |
| Launch | 3,000,000 | 150 |
| Grow | 8,000,000 | 250 |

---

## Pricing

Token-based. Standard rates per 1M tokens: **[OFFICIAL pricing page]**

| Model | Text in | Image in | Image out | Batch image out |
|---|---|---|---|---|
| gpt-image-2.5-flare / sunburst | $5.00 | $8.00 | $30.00 | $15.00 |
| gpt-image-2 | $5.00 | $8.00 | $30.00 | $15.00 |
| gpt-image-1.5 | $5.00 | $8.00 | $32.00 | $16.00 |
| gpt-image-1 | $5.00 | $10.00 | $40.00 | $20.00 |
| gpt-image-1-mini | $2.00 | $2.50 | $8.00 | $4.00 |

"Equal token rates don't mean equal cost per image: token consumption can
differ by model and quality setting." Partial images add 100 output tokens
each. Edits with reference images cost more input tokens because inputs are
always high-fidelity. **[OFFICIAL]**

OpenAI publishes no per-image table for 2.5 (it points to the calculator).
Measured output tokens at 2048×1152, identical for Flare and Sunburst:
**[COMMUNITY — Tosea, 41 calls]**

| quality | gpt-image-2 | 2.5 Flare / Sunburst | ≈ $ at $30/M |
|---|---|---|---|
| low | 157 | 157 | $0.005 |
| medium | 1,413 | 367 | $0.011 |
| high | 5,650 | 1,413 | $0.042 |
| xhigh | rejected | 2,511 | $0.075 |
| max | rejected | 5,650 | $0.170 |

At 3840×2160: 2.5 `high` 3,336 tokens (~$0.10), `max` 13,342 (~$0.40).
Official per-image table for the older ladder at 1024×1024 (`gpt-image-2`):
low $0.006 / medium $0.053 / high $0.211 — so 2.5 `max` at 1K ≈ $0.21.
**[OFFICIAL table for gpt-image-2; mapping to 2.5 is COMMUNITY]**

Non-square sizes "can sometimes produce fewer output tokens than square
sizes at the same quality"; "square images are typically fastest". **[OFFICIAL]**

---

## Request contract (`/v1/images/edits`) — what the reference actually says

**[OFFICIAL — API reference, images.edit / images.generate]**

| Param | Rule |
|---|---|
| `image` | png / webp / jpg, each < 50 MB, **up to 16** for GPT image models. |
| `prompt` | ≤ **32,000 characters** (characters, not tokens). |
| `mask` | PNG < 4 MB, same dimensions as the image, alpha channel required; transparent pixels = editable. With several images "it applies to the first". |
| `model` | `gpt-image-1`, `-1-mini`, `-1.5`, `-2`, `-2-2026-04-21`, `-2.5-sunburst[-2026-09-08]`, `-2.5-flare[-2026-09-08]`, `chatgpt-image-latest`. |
| `size` | `1024x1024`, `1536x1024`, `1024x1536`, `auto`; for gpt-image-2 / 2.5: custom `WIDTHxHEIGHT`, both divisible by 16, ratio 1:3–3:1, max 3840×2160, total 655,360–8,294,400 px, "above 2560×1440 experimental". |
| `quality` | `low` `medium` `high` (+ `xhigh` `max` on 2.5), default `auto`. |
| `input_fidelity` | `high`/`low`, **gpt-image-1 and 1.5 only** (1-mini: `low` only). "Omit for gpt-image-2" — and 2.5 rejects it. |
| `background` | `transparent` / `opaque` / `auto`; transparent needs png or webp; 2.5 fully supports both; gpt-image-2 transparent is preview. |
| `output_format` | `png` (default) / `jpeg` / `webp`; "using jpeg is faster than png". |
| `output_compression` | 0–100, jpeg/webp only. |
| `n` | 1–10. |
| `stream` / `partial_images` | 0–3 partials, each billed 100 output tokens. |
| `moderation` | `auto` (default) / `low` (generations; not listed on edits). |
| `safety_identifier` | replaces deprecated `user`. |
| `response_format` | deprecated; GPT image models always return `b64_json`. |
| `seed` | **does not exist**. |

Response: `data[].b64_json` (+ `revised_prompt` when the model rewrote the
prompt), `background`, `output_format`, `quality`, `size`, `usage{input_tokens,
input_tokens_details{text_tokens,image_tokens}, output_tokens,
output_tokens_details{…}, total_tokens}`. The schema still annotates `usage`
as "gpt-image-1 only" but 2.5 calls return it in practice (benchmarks read
token counts from it). **[OFFICIAL schema; COMMUNITY for 2.5 behaviour]**

Errors worth matching: `error.type = image_generation_user_error`,
`error.code = moderation_blocked` (with `moderation_details.moderation_stage`
∈ input|output and coarse `categories`; "should not be retried without
changing the prompt or inputs"), `invalid_input_fidelity_model`,
`"does not support quality 'xhigh'"` on gpt-image-2. **[OFFICIAL / COMMUNITY]**

Latency: "Complex prompts may take up to 2 minutes." Measured means at a
1,413-token render: gpt-image-2 37 s, Sunburst 28 s, Flare 20 s; at 5,650
tokens 83 / 60 / 34 s. **[OFFICIAL / COMMUNITY Tosea]**

---

## Official prompting guidance (GPT Image 2.5 prompting guide + cookbook)

Source: https://developers.openai.com/api/docs/guides/image-prompting (the
current 2.5 guide) and the archived cookbook recipes
`image-gen-models-prompting-guide` (gpt-image-2 era, "archived and may
reference outdated models") and `image-gen-1.5-prompting_guide`. Everything in
this section is **[OFFICIAL]** unless marked.

### (a) Preserving material / fabric texture from references

- "Name materials, lighting, colors, and the visual medium." "Describe framing
  and texture." Ask for real texture explicitly ("real skin texture, worn
  materials") and "avoid words that imply studio polish or staging"
  (cookbook).
- For edits, "identify what should change and what must stay the same" — the
  preserve list is where textures and materials go. Example prompt from the
  guide's furniture workflow ("Change furniture in a room"): "Preserve camera
  angle, room lighting, floor shadows, and surrounding objects. Photorealistic
  contact shadows and fabric texture." Clothing example: "with realistic
  fabric behavior."
- There is **no official statement** that a reference image's texture is
  transferred more faithfully than a text description. The guide treats a
  reference as a source of identity/style and the prompt as the place where
  texture is *named*. Do both.
- Nothing official on chenille / bouclé / velvet. The ARCHITECTURE invariant
  ("the English material noun outweighs the texture spec") has no OpenAI
  counterpart but is consistent with the guide's "name materials" instruction
  and with the community's "one explicit role per reference" rule.

### (b) Locking exact colours

- The guide never mentions hex codes, RGB, Pantone or swatch images. Colour is
  always words: "natural color balance", "strong color direction", "muted blues
  and grays", "match lighting, shadows, and color temperature to the original
  photo", "same facial features, proportions, and color palette".
- The preserve-list pattern is the official colour lock: list "color" among
  the things that must not change, and restate it every turn.
- **[COMMUNITY]** A September 2026 review of vendor docs confirms neither
  OpenAI nor Google mention hex (prompt-architects). LTX's help centre claims
  GPT Image models "tend to give the best color accuracy" with hex codes —
  vendor tutorial, no measurement. Nightjar's explanation: a hex is an sRGB
  coordinate, "it cannot define how a physical material will look"; the
  photo governs material and lighting, the hex only steers the target hue.
  Everypixel's 34-brief gpt-image-2 study found no warm cast in 136 evaluator
  comments and no colour correction needed on white/neutral surfaces — but
  fabric was not assessed. Atlas Cloud treats any "visible shade change from
  the approved source" as a QA fail and reports early 2.5 users flagging
  "detail drift, texture artifacts, and product-accuracy concerns".
- Net: hex in text + colour-patch image + the word "color" in the preserve
  list is the belt-and-braces approach; nothing official promises hex-level
  accuracy on a textured surface.

### (c) Camera, framing, shot type, lens — and prompt order

- "Request 'photorealistic' or 'real photograph' explicitly when that is the
  goal." Example: "Shot like a 35mm film photograph, medium close-up at eye
  level, using a 50mm lens."
- "Treat camera specifications as cues for appearance, not a guarantee of
  exact physical simulation." (cookbook: "detailed camera specs may be
  interpreted loosely".)
- "Describe body framing, relative scale, gaze, and interaction with
  objects"; "if layout matters, call out placement".
- Order: "For complex requests, organize the prompt as scene, subject,
  details, and constraints, using labeled sections." Cookbook: "write prompts
  in a consistent order: background/scene, subject, key details, then
  constraints", include the intended use ("product photo", "ad") to set the
  polish level. Nothing official says first-vs-last wins on conflict; the
  consistent-order rule is about maintainability and debuggability.
- Camera angle belongs in the **preserve list** for edits: "Do not change the
  background, camera angle, framing, or image quality" (clothing example);
  "Preserve camera angle, room lighting, floor shadows…" (furniture example).

### (d) Multiple reference images

- "Identify each input by number and purpose: subject, style, clothing, or
  background." Example: "Pass the scene photograph as image 1 and the dog
  photograph as image 2" → prompt "Place the dog from the second image into
  the setting of image 1". Cookbook: "Reference each input by index and
  description… describe how they interact."
- Order: the only documented positional effect is that the **mask applies to
  the first image**. No official statement that image 1 is otherwise
  privileged; numbering in the prompt is the mechanism. **[COMMUNITY]**
  guides put the identity / product reference first and label it the
  highest-priority constraint; older OpenAI vision guidance says the model
  has no inherent sense of which image "came first", so label explicitly.
- Max for reliable adherence: **no official number**. Official examples use
  2–5 inputs (person + three clothing refs; try-on with five). Hard cap 16.
  **[COMMUNITY]** consensus: "give each reference one role"; unassigned
  references are a named failure mode (cometapi, promptessor, fal).
- Labelling convention: "Image 1: product photo … Image 2: style reference …
  Apply Image 2's palette and texture to Image 1" is the cookbook/Replicate
  pattern; a reference that should contribute only one property should say
  what it must *not* transfer ("lighting reference only — use its large soft
  source… not its subject"). **[OFFICIAL pattern; COMMUNITY elaboration]**

### (e) Solid / plain studio backgrounds

- Official backdrop guidance is almost entirely about **transparency**: set
  `background="transparent"` *and* ask for an isolated subject in the prompt;
  "do not add a solid backdrop, checkerboard, scenery, or shadow"; "a drawn
  checkerboard is not transparency"; repeat the transparency requirement on
  later edits or they add an opaque scene.
- For opaque plain backdrops the examples simply state it: "white
  background", "plain forest background to clearly showcase the character".
  **[COMMUNITY]** e-commerce prompt sets use "nearly shadowless pure white
  background", "light gray seamless", "even studio light" and keep the backdrop
  line in the preserve list on every edit.
- An option for us: generate the product on `background: transparent` and
  composite the cyclorama ourselves — the official route to a pixel-stable
  background.

### (f) Masks vs full re-render

- Three edit modes are inferred from inputs: edit one image, generate from
  several references, edit a masked region.
- "Masking is entirely prompt-based" — the mask is guidance; the model "may
  not follow its exact shape with complete precision"; "when using a mask the
  prompt must describe the whole resulting image, not just the edit"
  (cookbook).
- "If a region must stay pixel-identical, composite the approved edit into
  the original image rather than relying on prompting." Without a mask "the
  whole frame is open to change". **[COMMUNITY measured]** pixel drift per
  single-change edit turn: gpt-image-2 5.6→8.1→11.4 %, Sunburst 4.1→6.8→9.9 %,
  Flare 3.8→6.7→9.2 % over three turns (Tosea); one Flare single-element edit
  changed only 0.22 % of pixels outside the region (Puter).

### (g) Prompt length and structure

- "Short prompts, descriptive paragraphs, JSON-like structures, instructions,
  and tags can all express the same intent. Choose the format that makes the
  requirements easiest to read and update rather than relying on special
  syntax." Cookbook: "for complex requests use short labeled segments or line
  breaks instead of one long paragraph"; "long prompts can work well, but
  debugging is easier" from a clean base; iterate with "small, single-change
  follow-ups".
- No official length target. Hard limit 32,000 characters. **[COMMUNITY]**
  one 2025 report of gpt-image-1 edits returning unrelated images around
  5–7k *tokens* of prompt; several guides argue long prompts bury hard
  constraints and cost input tokens.
- "Treat the prompt like a spec."

### Model choice and migration (official)

- "If GPT Image 2.5 Sunburst meets your quality requirements, then test GPT
  Image 2.5 Flare with the same prompts and inputs. Keep Sunburst when its
  quality advantage is necessary." Migrate one setting at a time; "repeat
  requests to measure consistency"; "repeated edits can still change details
  you intended to preserve"; "outputs can differ across models".
- Start with `low` for drafts; compare higher tiers for final assets, small
  text, identity-sensitive edits.

### Documented limitations

"Text rendering, consistency across generations, and precise composition
control." The model may rewrite the prompt (`revised_prompt`). **[OFFICIAL]**

---

## Practitioner findings — product / furniture / fabric

All **[COMMUNITY]**; sample sizes are small and most authors sell access to
the models.

- **Product photography is a strong category for text-to-image.** Everypixel's
  34-brief gpt-image-2 panel (4 pros, quality=high): product/food briefs mean
  9.81/10, all passed; evaluators flagged "evenly spaced droplets" and liquid
  physics as the tells, and the model ignored aspect ratios written in the
  prompt (all 34 came back 16:9 — use the `size` param, never prose).
- **Edit-with-references: 2.5 holds the product better than Nano Banana 2.1**
  in Fuser's same-prompt test (one shot each, 2026-10-06): GPT kept bottle,
  cap and label; NB2.1 restyled the cap. But on the *product shot from text*
  brief NB2.1 followed the staging (board, left light, shadow) while Flare
  swapped in a tabletop and a barely-visible shadow and added unrequested
  water droplets — i.e. GPT Image is more prone to "improving" the scene.
- **Material realism split:** apiyi and Curious Refuge both prefer Nano
  Banana Pro for "natural skin and surfaces", calling gpt-image-2 "slightly
  digital". Curious Refuge (Sunburst via Magnific, 4K): product swaps
  "convincing", "matched lighting and perspective and added wrinkles and
  imperfections", but faces showed "fractal-like", over-sharpened texture
  even at 4K, and "with every edit the image became slightly sharper, more
  saturated, and more artificial" over five passes. Recommendation: one or
  two edits per generation, then go back to a clean master.
- **Texture smoothing on product edits is a filed bug** (OpenAI forum,
  2026-09-03, gpt-image-2): "plastic", overly smooth skin "essentially always
  the same" across thousands of garment-recolour edits; five prompt styles
  from minimal to heavily structured; "strong product-lock instructions and
  repeated constraints do not reliably solve it"; garments hid it partly. No
  fix from OpenAI as of 2026-09-10. Expect the same flattening on low-relief
  pile (velvet, chenille) — bouclé loops and plecionka weave give the model
  more to hold on to.
- **Shape drift between generations:** Pixmax (one prompt, two images per
  model) saw Flare's "object proportions and spatial relationships vary more
  between generations than in GPT Image 2" and Sunburst interpreting exact
  position/scale "more loosely"; gpt-image-2 "gave the most reliable spatial
  results". Atlas Cloud's failure list for 2.5 product work: changed geometry,
  stretched proportions, extra units, colour shift, "new gloss, texture, or
  transparency", shadows not matching scene light, halos on alpha edges.
- **Colour:** no warm cast reported on gpt-image-2 (Everypixel); Puter's SSIM
  test found OpenAI's own published tuxedo edit shifted 16.9 % of pixels
  outside the region ("a slight overall color adjustment"), while their Flare
  run shifted 0.22 % — unrequested global colour drift is possible per call.
  Curious Refuge: 2.5 "matched a specified color grade more faithfully than
  Nano Banana Pro".
- **Working pattern everyone converges on** (Atlas Cloud, fal, promptessor,
  cometapi, nexscope): a "SKU protection list" / "Keep exactly" block
  (outline, proportions, colour and finish, count, orientation, camera angle,
  light direction) + a single "Change only" line + explicit prohibitions ("no
  redrawing, restyling, simplifying, inventing"; "no added shadows, text,
  props touching the product") + one variable per run + return to the last
  accepted output rather than repairing a drifted one + inspect at 100 % next
  to the source. Nexscope's fabric close-up prompt adds "do not invent
  stitching patterns" and warns the result is "an illustrative
  interpretation, not a measured macro photograph".
- **Flare vs Sunburst in practice:** identical token counts and price at every
  tier (Tosea); Sunburst ~1.4–1.8× slower; Sunburst "holds fine structure
  better… keeps neighbouring fine detail from merging at 4K on xhigh" (fal),
  "most polished… reflections, brushed metal, leather" (Pixmax), but in
  Puter's poster test Sunburst *added* unrequested scenery while Flare
  followed the brief. Atlas Cloud: Flare for cutouts / exploration, Sunburst
  "for a later, narrow retouch after the composition is accepted" and for
  "dense label, material, or protection requirements".
- **Nano Banana comparison for this use case:** no test covers upholstery.
  Tendencies across sources: GPT Image 2.5 better at keeping a referenced
  product's identity through an edit and at following colour grades; Nano
  Banana (Pro / 2.x) better at natural surface texture, scene/lighting
  staging and multi-image compositing with up to 14 refs; Nano Banana ignores
  refs outright 10–20 % of the time (see nano-banana-state.md), GPT Image
  instead drifts a little every call. For a fabric-swap where the swatch
  *texture* matters, the "digital/plastic" tendency is the risk to test for.

---

## Reproducibility

- **No `seed`, no `system_fingerprint`, nothing deterministic** on the Images
  API; Chat Completions' best-effort `seed` was itself only "mostly"
  deterministic and is absent from the Responses API. **[OFFICIAL by absence;
  COMMUNITY forum history]**
- OpenAI's own answer to "consistent sets": make a reusable reference
  (character anchor / approved product cutout), pass it as an input to every
  later call, restate the defining details and the preserve list in each
  prompt, "repeat requests to measure consistency", and test the whole edit
  sequence rather than single steps. **[OFFICIAL]**
- Every maskless edit re-renders the whole canvas; the only pixel-exact
  guarantee is compositing. **[OFFICIAL]**
- Practical set recipe **[COMMUNITY synthesis]**: lock one approved base
  render per product × angle; for each colour/fabric variant send that base
  as image 1, the swatch as image 2, the colour patch as image 3, a prompt
  that changes only upholstery and preserves everything else by name; keep
  `size`, `quality`, model snapshot (`-2026-09-08`) and prompt text
  byte-identical across the set; log `revised_prompt` and `usage` per call;
  never chain edits more than 1–2 deep.

---

## What `openai_images.py` gets right vs. what to change

Right **[OFFICIAL]**: model ids; `max_refs: 16`; explicit `quality` (never
`auto`); explicit `WIDTHxHEIGHT` multiples of 16 for both 2.5 models; no
`input_fidelity` for 2.5 plus a retry if a model ever rejects it; size
fallback to the three standard sizes; cost from `usage` at $5/$8/$30;
`moderation`-code classification; 600 s timeout.

Outdated or contradicting guidance:

1. Module docstring and ARCHITECTURE.md say edits go out "with
   `input_fidelity: high`" — false for 2.5 (and 2); the parameter is
   1.x-only. `send_fidelity = bool(cfg.get("input_fidelity", True))` also
   defaults to *sending* it for any model not in the table — flip the default
   to `False`. **[OFFICIAL]**
2. `default_quality: "high"` is the old "medium" budget on 2.5; for fabric
   macro fidelity default to `xhigh` (Flare) and offer `max` on Sunburst.
   **[COMMUNITY measured]**
3. `price_hint` "≈$0.01–0.13/obraz przy 1K" undershoots `xhigh`/`max`
   (≈$0.08 / ≈$0.21 at 1K-class sizes). **[COMMUNITY measured + OFFICIAL table]**
4. 2K rows for 3:4, 4:3 and 21:9 (3.98 M / 3.98 M / 3.92 M px) sit above the
   official 2560×1440 "experimental" line; either cap 2K at 3,686,400 px for
   those aspects or label them experimental in the UI. **[OFFICIAL]**
5. Comment "custom sizes are not accepted on every model/endpoint yet" is
   stale: custom sizes are documented for gpt-image-2 and both 2.5 models on
   both endpoints. Keep the fallback, fix the comment. **[OFFICIAL]**
6. `output_format: "png"` always: official note that jpeg is faster; keep PNG
   for masters, consider jpeg for preview tiers. **[OFFICIAL]**
7. No `mask` and no `background: transparent` path: the official pixel-stable
   route for a fixed cyclorama is a transparent cutout composited locally, or
   a mask over the upholstery; the current full re-render is exactly the
   "whole frame is open to change" case. **[OFFICIAL]**
8. `safety_identifier` not sent (optional; `user` is deprecated anyway).
   **[OFFICIAL]**
9. `studio/openrouter.py` still offers `openai/gpt-image-1` (shutdown
   2026-10-23) and `-1-mini` (2026-12-01). **[OFFICIAL]**
10. The prompt builder's "image N is …" numbering matches the official
    pattern; what it does not yet do is give each reference a single role and
    an explicit "do not transfer X from image N" clause, which every 2.5 guide
    treats as the difference between adherence and drift. **[OFFICIAL
    pattern; COMMUNITY emphasis]**

---

## Sources consulted this pass (2026-10-20)

Official:

- [Image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
- [GPT Image 2.5 prompting guide](https://developers.openai.com/api/docs/guides/image-prompting)
- [API reference — images.edit (Python)](https://developers.openai.com/api/reference/python/resources/images/methods/edit)
- [API reference — images.generate (Python)](https://developers.openai.com/api/reference/python/resources/images/methods/generate)
- [Model page — gpt-image-2.5-flare](https://developers.openai.com/api/docs/models/gpt-image-2.5-flare)
- [Model page — gpt-image-2.5-sunburst](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst)
- [Model page — gpt-image-2](https://developers.openai.com/api/docs/models/gpt-image-2)
- [Pricing](https://developers.openai.com/api/docs/pricing)
- [Deprecations](https://developers.openai.com/api/docs/deprecations)
- [Changelog](https://developers.openai.com/api/docs/changelog)
- [Cookbook — GPT Image models prompting guide (archived, gpt-image-2 era)](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide)
- [Cookbook — gpt-image-1.5 prompting guide (archived)](https://developers.openai.com/cookbook/examples/multimodal/image-gen-1.5-prompting_guide)
- [Cookbook — Generate images with GPT Image (archived, gpt-image-1)](https://developers.openai.com/cookbook/examples/generate_images_with_gpt_image)
- [Introducing ChatGPT Images 2.5](https://openai.com/index/introducing-chatgpt-images-2-5/) (403 on fetch; read via the forum mirror below)
- [OpenAI forum — Introducing GPT Images 2.5 in the API and ChatGPT](https://community.openai.com/t/introducing-gpt-images-2-5-in-the-api-and-chatgpt/1395897)
- [OpenAI forum — GPT Image 2 produces plastic-looking faces in product edit](https://community.openai.com/t/gpt-image-2-produces-plastic-looking-faces-in-product-edit/1394653)
- [OpenAI forum — GPT Image 2 masking issue](https://community.openai.com/t/gpt-image-2-masking-issue/1379510)
- [OpenAI forum — large prompt size bug (gpt-image-1)](https://community.openai.com/t/bug-in-the-new-image-generation-api-with-large-prompt-size/1239920)

Community / practitioner:

- [Tosea — GPT Image 2.5 complete guide (41-call API benchmark)](https://tosea.ai/blog/gpt-image-2-5-complete-guide)
- [Pixmax — Flare is 47% faster, but watch the quality trap](https://www.pixmax.ai/blog/gpt-image-2-5-review-flare-sunburst.html)
- [Puter — GPT Image 2.5 review (SSIM edit test)](https://developer.puter.com/blog/gpt-image-2-5-review/)
- [Curious Refuge — How good is GPT Image 2.5?](https://curiousrefuge.com/blog/open-ai-gpt-image-model-review)
- [Fuser — Nano Banana 2.1 vs GPT Image 2.5 same-prompt test](https://fuser.studio/articles/nano-banana-vs-gpt-image)
- [Everypixel — GPT Image 2.0 review, 34 briefs](https://research.everypixel.com/gpt-image-2-0/)
- [Atlas Cloud — GPT Image 2.5 product photography](https://www.atlascloud.ai/blog/tips/gpt-image-2.5-product-photography)
- [fal — How to use GPT Image 2.5](https://fal.ai/learn/tools/how-to-use-gpt-image-2-5)
- [Nexscope — 35 GPT Image 2.5 prompts for e-commerce product photography](https://www.nexscope.ai/blog/35-gpt-image-2-5-prompts-for-ecommerce-product-photography)
- [promptessor — GPT Image 2.5 prompting guide](https://promptessor.com/blog/gpt-image-2-5-prompting-guide)
- [CometAPI — How to prompt GPT Image 2.5](https://www.cometapi.com/how-to-prompt-gpt-image-2-5-like-a-pro/)
- [braindetox — Prioritizing constraints over changes](https://braindetox.kr/en/posts/gpt_image_2_5_prompt_guide_2026.html)
- [prompt-architects — Colour and palette prompting](https://prompt-architects.com/blog/563-colour-and-palette-prompting-getting-exact-colours)
- [prompt-architects — Editing and inpainting prompts for GPT Image 2](https://prompt-architects.com/blog/466-editing-and-inpainting-prompts-for-gpt-image-2)
- [Nightjar — Why does AI change my product's colour](https://nightjar.so/help-desk/why-does-ai-change-my-product-s-color-and-how-do-i-keep-it-accurate)
- [LTX help — Use HEX codes for exact colour matching](https://help.ltx.io/hc/en-us/articles/35704813868818-Use-HEX-codes-for-exact-color-matching)
- [apiyi — Nano Banana Pro vs gpt-image-2 e-commerce comparison](https://help.apiyi.com/en/nano-banana-pro-vs-gpt-image-2-ecommerce-product-image-comparison-en.html)
- [apiyi — image long prompt (32,000-char limit)](https://docs.apiyi.com/en/api-capabilities/image-long-prompt)
- [pydantic-ai issue #5413 — gpt-image-2 errors on input_fidelity](https://github.com/pydantic/pydantic-ai/issues/5413)
- [Kulfiy — GPT Image 2 input fidelity: leave it out](https://www.kulfiy.com/gpt-image-2-input-fidelity-why-you-should-leave-it-out/)
- [OrcaRouter — GPT-Image 2.5 sizes, pricing](https://www.orcarouter.ai/blog/gpt-image-2-5)
- [datanorth — ChatGPT Images 2.5 (claims Batch unsupported)](https://datanorth.ai/news/openai-launches-chatgpt-images-2-5)
- [Wikipedia — GPT Image (timeline)](https://en.wikipedia.org/wiki/GPT_Image)

---

## Changelog

### 2026-10-20 — Initial pass

First version. Established: current line-up (2.5 Flare / Sunburst, snapshot
2026-09-08), 16-image edit cap, 32,000-char prompt limit, custom-size rules
and the 2560×1440 experimental line, `input_fidelity` confined to 1.x models,
shutdown dates for gpt-image-1 (2026-10-23) / 1-mini / 1.5 (2026-12-01),
token rates, the measured quality-ladder shift (2.5 `high` ≈ 2 `medium`),
absence of any seed, official prompting rules (a)–(g), practitioner failure
modes for product work, and ten concrete deltas against `openai_images.py`.
