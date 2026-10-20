# Nano Banana — State as of 2026-10-20

## ⚠ Implications for current architecture (2026-10-20 pass — read first)

1. **`gemini-3.1-flash-image` (Nano Banana 2) is now DEPRECATED** (changelog, 2026-10-06: "no shutdown date announced"; migrate to `gemini-nano-banana-2.1`). `prompts/schemas/sofa.json` still describes it as "the recommended general-purpose production model". New Flash-tier default per Google: **`gemini-nano-banana-2.1`** (GA 2026-10-06, stable, ~half the price of NB2 at 1K/2K).
2. **`gemini-2.5-flash-image` is deprecated, and sources conflict on the shutdown date.** Gemini API deprecations page (fetched 2026-10-20): shutdown **2027-03-15**, replacement `gemini-3.1-flash-lite-image`. Pricing page text (same day): "will be shut down on October 2, 2026", migrate to 3.1 Flash Image or 3.1 Flash Lite Image. An earlier search snippet of the deprecations page showed 2026-10-02. Treat 2027-03-15 as the newest official statement but unconfirmed; the deprecations page also says all dates are "earliest possible dates". Whichever is right, it is legacy: 1K only, 3 refs.
3. **No seed parameter is documented for any Gemini image model.** The pipeline's `seed hint: N` line (`app-v2/studio/mappings.py`) is only prompt text, not an API seed. See "Reproducibility".
4. **Thinking cannot be disabled on any Gemini 3 image model**; `thinking_level` is configurable on NB2.1 (minimal / medium default / high) and 3.1 Flash + Flash-Lite (minimal default / high). Thinking tokens are billed; up to two interim "thought images" are generated but not charged.
5. `app/core/cost_tracker.py` assumes 258 input tokens per image for `gemini-3-pro-image`; the official pricing page states **560 tokens (~$0.0011)** for Pro. `gemini-nano-banana-2.1` is missing from the cost table (see pricing below).
6. Official Google prompt guidance says "Describe what you want, not what you don't" (no negative-prompt field). Pipeline prompts use `NEGATIVE (must not appear...)`, `TEXTILE — must not appear:` and `No people, no human figures...` lines. Community evidence is mixed (see Practitioner findings), so this is a divergence from official guidance, not a proven defect.

Older implications from earlier passes remain in the section further below (some are superseded by the above).

---

## 2026-10-20 refresh

### Model lineup (official: Gemini API pricing, deprecations, changelog, model pages)

| Model ID | Name | Status | Released | Std price/img | Batch price/img | Notes |
|---|---|---|---|---|---|---|
| `gemini-nano-banana-2.1` | Nano Banana 2.1 | **Stable / GA**, no shutdown date | 2026-10-06 | 1K $0.0336, 2K $0.0504, 4K $0.113 | 1K $0.0168, 2K $0.0252, 4K $0.0567 | Update to NB2: better visual quality, prompt adherence, multi-turn consistency, text rendering; wide ratios 1:4/4:1/1:8/8:1 at 1K-4K; tiling-artifact fix on wide 2K/4K. No 512px. 131,072 in / 32,768 out. Inputs text/image/video/PDF. |
| `gemini-3.1-flash-image` | Nano Banana 2 | **Deprecated 2026-10-06**, no shutdown date | 2026-05-28 (GA) | 0.5K $0.045, 1K $0.067, 2K $0.101, 4K $0.151 | 0.5K $0.022, 1K $0.034, 2K $0.050, 4K $0.076 | Replacement: `gemini-nano-banana-2.1` |
| `gemini-3.1-flash-lite-image` | Nano Banana 2 Lite | Stable, no shutdown date | 2026-06-30 | 1K only: $0.0336 | $0.0168 | "Not optimized for multiple reference inputs or multi-turn sequential editing"; no Google Search grounding |
| `gemini-3-pro-image` | Nano Banana Pro | **Stable**, no shutdown date | 2026-05-28 (per deprecations page; model page says "latest update Nov 2025") | 1K/2K $0.134, 4K $0.24 | 1K/2K $0.067, 4K $0.12 | "Premium choice for the most complex visual tasks"; 65,536 in / 32,768 out; image input = 560 tokens (~$0.0011); no Flex/Priority on model page but pricing page lists Priority rates |
| `gemini-2.5-flash-image` | Nano Banana (original) | **Deprecated**; shutdown 2027-03-15 (deprecations page) vs 2026-10-02 (pricing page text) — CONFLICT | 2025-10-02 (GA) | 1K (<=1024px) $0.039 | $0.0195 | "Legacy pioneer"; 1K only |

Shut down already (deprecations page): `gemini-3.1-flash-image-preview` and `gemini-3-pro-image-preview` (2026-06-25), `gemini-2.5-flash-image-preview` (2026-01-15), `gemini-2.0-flash-preview-image-generation` (2025-11-14), `imagen-3.0-generate-002` (2025-11-10), `imagen-4.0-*-generate-preview-06-06` (2026-02-17), `imagen-4.0-generate-001` / `-ultra-` / `-fast-` (2026-08-17; replacement `gemini-nano-banana-2.1`). The May snapshot below that lists `-preview` IDs and Imagen 4 as live is obsolete.

Token pricing (pricing page): NB2.1 output $30/1M image tokens (1K 1,120 tok; 2K 1,680; 4K 3,780), input $1.50/1M (batch $0.75). NB2 output $60/1M, input $0.50/1M. Lite $30/1M out, $0.25/1M in. Pro $120/1M out, $2.00/1M in. Grounding (NB2.1, NB2): 5,000 free requests/month shared across Gemini 3+, then $14 per 1,000.

Pricing conflict: third-party coverage of the NB2.1 launch quotes 4K at $0.0756; the official pricing page (fetched 2026-10-20) gives $0.113 (3,780 tokens x $30/1M, internally consistent). Official page used. Note the 4K token count for NB2.1 (3,780) is higher than NB2 (2,520), so 4K is only ~25% cheaper than NB2, while 1K/2K are ~50% cheaper.

Caveat: pricing/deprecation tables were read through a summarising fetch tool, not raw HTML; re-verify in the console before changing billing code.

### Reference-image limits and resolutions

| Item | NB2.1 | NB2 (3.1 Flash) | Lite | Pro |
|---|---|---|---|---|
| Total refs per request | 14 | 14 | 14 | 14 |
| High-fidelity object refs | 10 | 10 | 14 | 6 |
| Character-consistency refs | 4 | 4 | n/a | 5 |
| Style refs | n/a | n/a | n/a | 3 |
| Resolutions | 1K/2K/4K (default 1K) | 0.5K/1K/2K/4K | 1K only | 1K/2K/4K |
| Aspect ratios | 10 standard + 1:4, 4:1, 1:8, 8:1 | 14 (same set) | 10 standard | 10 standard |

Source: ai.google.dev image-generation guide table. The page text was flattened by the fetch tool, so the column mapping is INFERRED. Third-party corroboration for Pro (6 objects / 5 characters / 3 style within 14 total): GlobalGPT, Morphic. A Morphic listing for NB2 says "5 characters, 14 objects", which disagrees with the inferred 10/4 — unresolved conflict, re-check against the live page. Uppercase "K" is mandatory for `image_size` ("1k" is rejected). Gemini 3 image models default to 1K.

### What Google officially says about prompting (OFFICIAL)

Sources: ai.google.dev image-generation guide; Google Developers Blog "How to prompt Gemini 2.5 Flash Image"; Vertex AI "Gemini image generation best practices"; blog.google "Nano Banana Pro prompt tips"; DeepMind prompt guide. The Gemini API guide has NO dedicated best-practice section for texture, colour, ordering or labelling (only templates).

- **Structure (a):** Subject, composition, action, location, style (blog.google). DeepMind: Style, Subject, Setting, Action, Composition. "The more specific you are, the more control you have." Describe the scene; do not list keywords.
- **Material / texture:** Name materials and surface detail explicitly (Vertex: "naming materials, patterns, and silhouettes rather than a general style"; example "ornate elven plate armor, etched with silver leaf patterns"). Photorealistic template has a placeholder to emphasise "key textures and details". Product example: "matte black ... on a polished concrete surface". Nothing in official docs on fabric-weave vocabulary specifically.
- **Colour:** Official docs name palettes/schemes in words ("a vibrant color palette", "two-toned scheme", colour grade phrases). **No official statement on HEX codes or on flat colour-patch reference images.** (Gap — neither endorsed nor discouraged.)
- **Camera / framing:** "Photographic and cinematic language": wide-angle, macro, low-angle, 85mm portrait lens, Dutch angle; template "Shot from a [camera angle] with a [lens type]"; product template: studio-lit, three-point softbox, specified angle, end with "Ultra-realistic, with sharp focus on [key detail]". **No official rule for whether framing goes first or last.** Vertex: split complex scenes into steps (background, foreground, focal element).
- **Multi-image references (d):** blog.google: "Clearly define the role of each uploaded image" — "Use Image A for the character's pose, Image B for the art style, and Image C for the background environment." The 2.5 Flash Image blog refers to images by position ("the blue floral dress from the first image"). Mixed aspect-ratio inputs: "the model will adopt the aspect ratio of the last image provided" (2.5-era statement, not re-confirmed for Gemini 3 models). **No official statement that image order matters, no official recommended max for reliable adherence** other than the per-type limits above. No official subject/style/texture labelling convention beyond role statements; the structured categories are objects / characters / style (Pro). Official sample code places the text prompt first and images after in `contents`; no rule is stated.
- **Background (e):** Only "The background must be white" (sticker), "soft, solid-colored background" (London example), "a vast, empty [color] canvas". Nothing about consistency across a set. For multi-image sets blog.google says generate one image at a time.
- **Edits:** "Keep everything else in the image exactly the same, preserving the original style, lighting, and composition." "Do not change any other elements of the image." Multi-turn conversation is "the recommended way to iterate"; pass thought signatures back (Vertex). For drift after many edits the 2.5 blog says restart a new conversation with a detailed description.
- **Negative prompts:** "Describe what you want, not what you don't" ("no cars" -> "an empty, deserted street with no signs of traffic").
- **Image intent:** Use "create an image of ..." otherwise the model may answer in text.
- **Limitations (blog.google):** small text/fine details can fail; complex blends or lighting changes can produce artifacts; character consistency across edits may vary.
- **JSON / structured prompts:** Google's guides never mention JSON; they recommend narrative description (reported by a third party, human-ai-human.org; consistent with the guides read here).
- **Prompt length:** No official limit or degradation statement. Context window 32,768 (older Flash) / 65,536 (Pro in) / 131,072 (NB2.1 in).

### Reproducibility (seed, temperature, thinking)

- Gemini API `generationConfig.seed` is documented generically as best-effort ("deterministic output isn't guaranteed"). None of the image-model pages read (NB2.1, Pro model pages, image-generation guide, changelog) mention seed, temperature or system-instruction support. Third-party blog (prompt-architects.com, 2026) says Google publishes no seed for Gemini image generation and that `ImageConfig` has only aspect ratio and image size. Forum/GitHub reports of non-determinism with fixed seed + temperature concern `gemini-2.5-pro` text, not image models. A PixVerse CLI feature request lists `gemini-3-pro-image-preview` among seed-capable models (user request, not vendor documentation). Net: determinism is NOT available/guaranteed on current image models; treat any seed as unverified.
- Thinking: always on for Gemini 3 image models ("cannot be disabled in the API"); `thinking_level` NB2.1 minimal/medium(default)/high; NB2 and Lite minimal(default)/high; Pro has no level documented on the pages read. Interim thought images are not charged; thinking tokens are.
- System instructions: the Vertex capability tables (May pass) list support; the Gemini API pages read today do not mention them. Still unverified by a test call.

### Practitioner findings (COMMUNITY / vendor blogs — not Google guidance)

- **[2026-10-06] Fuser (fuser.studio, single run, 2K, no retries):** Hex test "matte ceramic ... glazed in #1F6F5C" on NB2.1: glaze came out "darker and greyer ... leaning slightly yellower"; tied with FLUX.2 pro; recommendation to check brand colours on the output. N=1.
- **[2025-11] minimaxir.com:** hex codes in a prompt ("#9F2B68-and-#00FF00" fur colours) were followed for stylised fur (not measured); ALL CAPS and "MUST" help (anecdotal, "threats do tend to improve adherence"); inline "Do not include any text or watermarks" worked, but "do not generate a digital illustration" did not stop illustration style; long structured prompts (916-token HTML, ~2,600-token JSON) were usable; no systematic degradation curve measured. Specifying lighting and background together helped them complement each other.
- **[2025-09-11] thematerialbrief (NunoX, Jac Hsieh):** Nano Banana preserves fabric texture better than other tools tried; solid-colour recolouring works, multi-colour pattern recolouring fails; a pasted swatch plus blank 3D model gave oversized/distorted pattern scale; precise textile terminology and 6-8 iterations needed; "not final production photography".
- **[2026-10-08] promptzone (NB2.1 guide):** structure "Deliverable + subject + setting + composition + lighting + exact text + details to preserve"; assign each ref a role; "use as few references as the task requires, since extra uploads can add conflicting instructions"; "Preserve exactly" is not pixel-level; "seamless warm ivory background"; framing phrases such as "Show the whole bag", "three-quarter front view".
- **[2026-10] Fuser prompt guide:** keyword-only prompt let the model invent props (carafe, paper filter) where a sentence-form prompt did not; naming what must stay unchanged beats a general "keep everything else"; plain setting description ("plain white tiled wall with nothing else on it") prevented a stray extra board on Pro; one change per edit pass.
- **Runware NB2.1 docs (vendor):** array order is the numbering ("image 1" = first entry); name each image by position AND content ("the green e-bike from image 2") so reordering is safe; each reference should have one role (subject to keep, product to place, setting, look to copy); add a scope clause to style refs ("take nothing else from it"); state the count ("exactly once"); describe lighting once for the final scene; plain reference backgrounds are easier.
- **JSON vs prose:** Chase Jarvis side-by-side (secondhand, Pro) found essentially identical results; one blog (fanchai.app) reports a single-run JSON win on a haze effect; minimaxir says JSON "silly but works". No controlled benchmark exists.
- **Prompt length:** only unmeasured assertions ("past a point every extra adjective costs adherence"; contradictions confuse the model). No controlled study found.
- **Not found:** no credible source on the "framing collapse to a hero shot when a swatch reference is attached" (our invariant #4); no source testing a flat colour-patch image for exact colour; no source quantifying the "velvet stereotype" (our invariant #1). These remain project-internal findings. One untested hypothesis only: the 2.5-era note that the model adopts the aspect ratio of the last image supplied could interact with close-up swatch crops, but the pipeline sets `aspect_ratio` explicitly, so this is not established.
- **Peak-hour reliability, ignore rate (10-20%) and other earlier community items** from the May pass were not re-verified.

### Pipeline contradictions with official guidance (as seen in code 2026-10-20)

1. Model: pipeline treats `gemini-2.5-flash-image` as current and `gemini-3.1-flash-image` as recommended; the former is deprecated, the latter deprecated 2026-10-06.
2. Negative / "must not appear" phrasing (`mappings.py` freeform prompt, `TEXTILE — must not appear`, `NEGATIVE (...)`): official guidance prefers positive description. Community evidence mixed.
3. `seed hint: N` as a prompt line: not a documented control; no effect is documented.
4. Label-style blocks (`TASK:`, `BRIEF:`, `ART DIRECTION:`, `LIGHT:`, `CAMERA:` ...) and pipe/colon fragments rather than narrative sentences: official guides repeatedly say "describe the scene", not keyword lists. (Prior pass already flagged notes-blob placement.)
5. `cost_tracker.py` Pro input tokens (258) differ from the official 560; NB2.1 absent.
6. No contradiction found (consistent with official guidance): naming the material noun plus texture spec; assigning an explicit role to every reference image and scoping what to copy ("copy ONLY its yarn construction"); explicit preserve lists; thought-signature history passing; explicit aspect_ratio / image_size with uppercase K.

---

## Prior sections (earlier passes — model IDs/status/prices below are superseded where they conflict with the 2026-10-20 section above)

## 2026-08-27 official-docs update

Google's image-generation guide was updated on 2026-08-26. The current stable
production IDs are `gemini-3.1-flash-image` (Nano Banana 2, recommended default)
and `gemini-3-pro-image` (precision / professional asset production). The older
`-preview` identifiers used in the May research below are superseded. Nano
Banana 2 supports 1K, 2K and 4K output and is explicitly positioned by Google
as the best general balance of quality, consistency, price and latency. It also
excels at multiple-reference processing; the catalog pipeline therefore uses
it by default and keeps Pro as the highest brand-consistency option.

**Superseded 2026-10-20:** NB2 deprecated, NB2.1 is the Flash-tier successor.

Primary sources:

- https://ai.google.dev/gemini-api/docs/image-generation
- https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-image
- https://ai.google.dev/gemini-api/docs/pricing

The historical notes below remain useful for failure modes and prompt lessons,
but model names/status from the May snapshot must not override this update.

---

## ⚠ Implications for current architecture (May–Aug passes; partly superseded)

1. **`gemini-2.5-flash-image-preview` is dead.** It was shut down January 15, 2026. Any code referencing that model ID will get a 404/model-not-found error. The stable replacement is `gemini-2.5-flash-image` (no `-preview` suffix). The sofa schema rationale mentions "current Nano Banana max output" at 2K — this is still accurate for that model ID, but see resolution section below.

2. **`number_of_images` is broken in the Python SDK for Nano Banana models.** Documented as supporting up to 10 output images per prompt, but passing `number_of_images` to `GenerateContentConfig` throws a validation error (`Extra inputs are not permitted`). Workaround: loop single-image calls, or use `imagen-4.0-generate-001` via `generate_images()` if batch output is needed. GitHub issue #1534 on `googleapis/python-genai` is open with no ETA. (2026-10-20: `imagen-4.0-*` is now shut down as of 2026-08-17, so that workaround no longer exists; status of issue #1534 not re-checked.)

3. **Thinking tokens add unbounded cost on `gemini-3-pro-image-preview`.** Thinking is on by default and cannot be disabled on Pro tier. Simple prompts add $0.002–$0.006; complex multi-reference prompts add 5–15% to effective per-image cost. The leg-pipeline-designer's use of multi-reference compositing (base sofa + leg reference + optional fabric swatch) falls in the middle of this range.

4. **Input image token cost changed.** The changelog records a reduction from 1,290 to 258 tokens per input image for `gemini-2.5-flash-image` on November 4, 2025. This means editing/reference workflows are cheaper than the launch pricing. Verify against official pricing page before each billing cycle.

5. **`gemini-2.5-flash-image` deprecation scheduled October 2, 2026.** Official migration path is `gemini-3.1-flash-image-preview`. No auto-redirect is confirmed at time of writing. (Superseded: see 2026-10-20 item 2.)

6. **NEW 2026-05-11 — Scene/environment adherence failure in generator.py is consistent with documented model behavior.** The hardcoded "Neutral studio backdrop" line appearing before a buried environment description in a `notes` blob at the end of the prompt represents the worst possible arrangement for this model family. Two independent sources confirm: (a) negative/constraint instructions near the top anchor the model's output mode; (b) when the same topic appears in multiple places in a prompt, the model may stop processing after the first relevant match. The environment description will be partially or fully overridden by the earlier studio line in a significant share of calls. This is not stochastic noise — it is a predictable structural failure. See "Scene/environment adherence" section below for details.

---

## Model lineup (May 2026 snapshot — SUPERSEDED, kept for history)

| Model ID | Tier | Status | Price/img (std) | Batch Price/img | Max refs | Max out res | Deprecation |
|---|---|---|---|---|---|---|---|
| `gemini-2.5-flash-image` | Flash | GA (stable) | $0.039 (1K) | $0.0195 | 3 | 1024×1024 | Oct 2, 2026 |
| `gemini-3.1-flash-image-preview` | Flash 2 | Preview | $0.067 (1K) / $0.101 (2K) / $0.151 (4K) | 50% off | 14 | 4096×4096 | Not set |
| `gemini-3-pro-image-preview` | Pro | Preview | $0.134 (1K–2K) / $0.240 (4K) | 50% off | 14 | 4096×4096 | Not set |

**Previously active — now shut down:**
- `gemini-2.5-flash-image-preview` — shut down January 15, 2026 (replaced by `gemini-2.5-flash-image`)
- `gemini-2.0-flash-exp-image-generation` — shut down November 11, 2025
- `imagen-3.0-generate-002` — shut down November 10, 2025

**Imagen 4 family (separate API, not Nano Banana):** `imagen-4.0-fast-generate-001` ($0.02), `imagen-4.0-generate-001` ($0.04), `imagen-4.0-ultra-generate-001` ($0.06). These use a different SDK call (`generate_images` not `generate_content`) and support `number_of_images` properly. Deprecation: June 24, 2026. Replacement listed as Nano Banana models. (2026-10-20: shut down 2026-08-17 per deprecations page.)

---

## Pricing detail

Pricing is token-based. Input images are billed as input tokens; output images are billed as output image tokens at a much higher per-token rate than text output.

### `gemini-2.5-flash-image`

| Component | Standard | Batch | Flex | Priority |
|---|---|---|---|---|
| Text input | $0.30/1M tok | $0.15/1M tok | $0.15/1M tok | $0.54/1M tok |
| Input image | ~$0.0001/img (258 tok × $0.30/1M) | same discount | — | — |
| Output image (≤1024px) | $0.039/img (1,290 tok × $30/1M) | $0.0195/img | $0.0195/img | $0.0702/img |

**Note on input image token cost:** As of November 4, 2025, input images for this model consume 258 tokens (down from 1,290 at launch). At $0.30/1M input tokens, each reference image costs approximately $0.000077. This is negligible even at 3 refs per call.

### `gemini-3.1-flash-image-preview` (now `gemini-3.1-flash-image`, deprecated)

| Component | Standard | Batch |
|---|---|---|
| Text/image input | $0.50/1M tok | $0.25/1M tok |
| Output image 512px | $0.045/img (747 tok × $60/1M) | $0.022/img |
| Output image 1K | $0.067/img (1,120 tok × $60/1M) | $0.034/img |
| Output image 2K | $0.101/img (1,680 tok × $60/1M) | $0.050/img |
| Output image 4K | $0.151/img (2,520 tok × $60/1M) | $0.076/img |

Input image token cost not separately confirmed for this model at time of writing. Assumed same tier rate as text input ($0.50/1M).

### `gemini-3-pro-image-preview` (now `gemini-3-pro-image`, stable)

| Component | Standard | Batch | Flex | Priority |
|---|---|---|---|---|
| Text/image input | $2.00/1M tok | $1.00/1M tok | $1.00/1M tok | $3.60/1M tok |
| Input image | ~$0.0011/img (per third-party source; confirmed 560 tok on official page 2026-10-20) | — | — | — |
| Output image 1K–2K | $0.134/img | $0.067/img | $0.067/img | — |
| Output image 4K | $0.240/img | $0.120/img | $0.120/img | — |
| Thinking tokens | $12.00/1M tok (standard) | — | — | — |

**Conflict:** One third-party source (aifreeapi.com) states $120/1M output tokens for Pro image; official pricing page quotes $0.134 per 1K–2K image (implying ~$134/1M output image tokens). These are consistent. The $12/1M thinking token rate is from third-party analysis and has not been independently verified against the official pricing page in this pass.

---

## Request format (Python SDK `google-genai`)

Install: `pip install google-genai`

### Basic text-to-image

```python
from google import genai
from google.genai import types

client = genai.Client(api_key="YOUR_API_KEY")

response = client.models.generate_content(
    model="gemini-2.5-flash-image",
    contents="A studio photo of a mid-century modern sofa, warm oak legs, \
cream boucle upholstery, neutral grey backdrop, three-quarter angle",
    config=types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio="4:3"),
    ),
)

for part in response.candidates[0].content.parts:
    if part.inline_data:
        with open("output.png", "wb") as f:
            f.write(part.inline_data.data)
```

(2026-10-20: swap `model` for `gemini-nano-banana-2.1`; for 2K/4K add `image_size="2K"` to `ImageConfig` — the repo's `generator.py` uses `image_size` with google-genai 2.0.0; uppercase K required.)

### Multi-image reference (base product + leg reference)

```python
from PIL import Image

base_sofa = Image.open("data/base-products/sofa-001.jpg")
leg_ref   = Image.open("legs/tapered_walnut_front34l.png")

response = client.models.generate_content(
    model="gemini-2.5-flash-image",
    contents=[
        "Edit the sofa in the first image to use the leg style from the second image. "
        "Preserve: frame geometry, cushion count, stitching pattern, camera angle, "
        "perspective, and upholstery color. Replace only the legs with the tapered "
        "walnut style shown. Match shadow direction to the existing light source.",
        base_sofa,
        leg_ref,
    ],
    config=types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio="4:3"),
    ),
)
```

**For `gemini-3.1-flash-image-preview` or `gemini-3-pro-image-preview`:** same structure; up to 14 images in the `contents` list; add `resolution` key to `ImageConfig` if targeting 2K/4K output (`image_config=types.ImageConfig(aspect_ratio="4:3", resolution="2K")`). Verify exact `resolution` parameter name against SDK docs — parameter spelling changed between preview releases. (2026-10-20: the repo's generator.py notes google-genai 2.0.0 uses `image_size`.)

### Extracting thought signatures (multi-turn)

```python
# Pass thought signatures back on follow-up edits to maintain context
thought_sigs = [
    p.thought_signature
    for p in response.candidates[0].content.parts
    if hasattr(p, "thought_signature") and p.thought_signature
]
# Include in next turn's contents alongside the generated image
```

### System instruction support

`gemini-2.5-flash-image` supports system instructions per Vertex AI documentation. Use `system_instruction` field in `GenerateContentConfig`. `gemini-3.1-flash-image-preview` and `gemini-3-pro-image-preview` also list system instructions as supported per Vertex AI capability tables.

```python
config=types.GenerateContentConfig(
    system_instruction="You are a product photography assistant. Always preserve "
                       "the camera angle, perspective, and product identity from the "
                       "reference image. Never redesign the product.",
    response_modalities=["IMAGE"],
    image_config=types.ImageConfig(aspect_ratio="4:3"),
)
```

System instruction support for image generation endpoints is listed in capability tables but is not prominently documented with examples. Treat as best-effort until independently verified with a test call.

---

## Capability matrix (May 2026 snapshot; see 2026-10-20 section for current IDs, reference limits and resolutions)

| Capability | `gemini-2.5-flash-image` | `gemini-3.1-flash-image-preview` | `gemini-3-pro-image-preview` |
|---|---|---|---|
| Max reference images/call | 3 | 14 | 14 |
| Max output resolution | 1024×1024 | 4096×4096 | 4096×4096 |
| Supported aspect ratios | 10 (see below) | 14 (see below) | 10 (see below) |
| Multi-image composition | Yes, basic blending | Yes, improved | Yes, best |
| Text rendering quality | Moderate (known weak area) | Improved | Best in lineup |
| Identity/object preservation | Good for single ref | Good–Very Good | Very Good |
| Character consistency | Good | Better | Best |
| Thinking / reasoning | Not supported | Supported (on by default) | Supported (on by default, cannot disable) |
| System instructions | Yes (documented) | Yes (documented) | Yes (documented) |
| Google Search grounding | No | Yes | Yes |
| Context caching | No | No | No |
| Function calling | No | No | No |
| Max input tokens | 32,768 | 131,072 | 65,536 |
| Max output tokens | 32,768 | 32,768 | 32,768 |
| SynthID watermark (invisible) | Yes | Yes | Yes |
| Transparent PNG output | No | No | No |

### Supported aspect ratios

**`gemini-2.5-flash-image`** (10 ratios):
`1:1`, `3:2`, `2:3`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`

**`gemini-3.1-flash-image-preview`** (14 ratios):
All 10 above plus `1:4`, `4:1`, `1:8`, `8:1`

**`gemini-3-pro-image-preview`** (10 ratios):
`1:1`, `3:2`, `2:3`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`
(Wide and tall extremes `1:4`, `4:1`, `1:8`, `8:1` not listed in Vertex AI docs for this model)

### Resolution output token counts (`gemini-3.1-flash-image-preview`)

| Resolution | Output tokens | Std cost | Batch cost |
|---|---|---|---|
| 512px (0.5K) | 747 | $0.045 | $0.022 |
| 1K (1024px) | 1,120 | $0.067 | $0.034 |
| 2K (2048px) | 1,680 | $0.101 | $0.050 |
| 4K (4096px) | 2,520 | $0.151 | $0.076 |

---

## Scene/environment adherence — findings (2026-05-11)

This section was added in response to a reported failure in Nano Sofa Studio where picking a named environment preset (e.g. "Loft industrial", "Salon skandynawski") produces a neutral studio shot instead of the specified scene. The following are factual findings only.

### 1. Prompt structure and where scene context must appear

Every official source and community analysis consulted agrees on the same ordering: **Subject → Action → Location/Scene → Composition → Style**. The Google Cloud "ultimate prompting guide for Nano Banana" explicitly places location/context in the third position, after subject and action, before style. The Google DeepMind prompt guide lists Setting as one of five primary components alongside Subject, Style, Action, and Composition — not as a trailing annotation.

The Vertex AI Gemini 3 prompting guide contains a documented finding on context processing: "when information is presented in multiple places across a source of context, the model can sometimes stop processing after the first relevant match." This is confirmed in the negative-constraint ordering guidance: negative/constraint instructions placed too early (before the main task) cause those constraints to be over-weighted. The guide recommends placing negative constraints and quantitative restrictions **last**, with task description and context front-loaded.

**Finding:** Placing "Neutral studio backdrop" as a top-level block early in the prompt, then appending the actual environment as a buried pipe-separated tail, is directly opposite to both the documented ordering model and the constraint-placement guidance. The studio line functions as an early constraint anchor that the model processes before reaching the environment description.

### 2. Instruction ordering sensitivity and "first vs last" conflict behavior

No official Google documentation explicitly states "first instruction wins" or "last instruction wins" for image generation. However, the Vertex AI Gemini 3 prompting guide behavior is consistent with a **first-match bias** for context anchoring: the model may stop processing a topic after encountering its first relevant instance in the prompt. This is a text-LLM-level behavior, not specific to image generation.

An independent community analysis (Max Woolf, minimaxir.com, November 2025) found that Nano Banana responds well to capitalized "MUST" statements and explicit emphasis but does not formally quantify ordering bias.

**Finding:** No primary-source evidence isolates first-vs-last ordering for contradictory image generation instructions specifically. Based on the text-model prompting documentation and the "stop after first match" behavior described above, the early "studio" line is the likely dominant signal when the environment override appears only at the tail. This is inferred from adjacent documented behavior, not directly measured.

### 3. "Notes blob" placement and under-weighting

No Google documentation describes a prompt region called "notes" or "additional notes" as a first-class prompt section. The pipe-separated `ADDITIONAL NOTES: time of day: ... | environment: ...` pattern does not correspond to any documented prompt template from Google for Nano Banana. Based on the general prompting guidance ("describe the scene, don't just list keywords"), a pipe-delimited keyword blob is specifically the format most likely to be under-weighted relative to a narrative sentence in the main prompt body.

**Finding:** The environment description appended as a notes blob will receive less weight than the same content expressed as a narrative sentence in the primary prompt body. Combining this with early-anchor conflict makes the current structure doubly degraded.

### 4. Scene text-only vs reference image for environment

The Google AI documentation states: "If you upload multiple images with different aspect ratios, the model will adopt the aspect ratio of the last image provided." This confirms the model pays attention to reference image content as a strong signal. Multiple community sources and the Google DeepMind e-commerce use-case description confirm that providing a reference scene image produces more reliable environment adherence than text description alone.

For the 3.1 Flash and Pro tiers, up to 14 reference images are supported, which allows a base product image + optional leg/swatch references + a scene reference image simultaneously. For `gemini-2.5-flash-image` (3-ref cap), a scene reference image consumes the third slot, leaving no room for additional product references.

**Finding:** A scene reference image produces stronger environment adherence than text description. For text-only scene presets (the current "pick from list" UX), scene adherence can be improved by: (a) using richer narrative description rather than keywords ("a loft apartment with exposed brick walls, raw concrete floors, steel-frame windows, warm Edison-bulb lighting casting soft shadows at 7pm" rather than "loft industrial"), (b) explicitly naming floor material, wall treatment, light source type, and color temperature — these are specifically called out in the official best-practices guide as adherence-improving details, (c) moving scene description to a primary narrative block before style instructions.

Community sources also confirm that explicit lighting direction and color temperature language in the scene description reduces background-product lighting mismatch.

### 5. Conflicting instructions — observed behavior summary

The Google community forum thread at discuss.ai.google.dev documents that Nano Banana Pro ignores reference images and prompts approximately 10–20% of the time outright (confirmed by multiple developers as of December 2025). For the scene adherence problem specifically, the conflict is structural rather than stochastic: the "studio" line is not a random miss but a consistent overriding anchor.

The forum thread workaround of adding "Analyze image inputs strictly for the established [style]" as a preparatory instruction before the main prompt aligns with the Vertex AI guidance that behavioral constraints placed in the system instruction (or at the very top of the prompt) anchor the model's reasoning process.

**Finding:** Contradictory instructions where the undesired output mode (studio backdrop) appears earlier in the prompt will favor the earlier instruction in a substantial share of calls. This is consistent across the text-LLM and image-generation prompting documentation consulted, even though no official source provides an exact percentage.

### 6. Polish text mixed into an English prompt

No documentation from Google addresses cross-language mixing within image generation prompts specifically. Gemini 3 multilingual benchmarks cite 140-language support with high accuracy (third-party report, skywork.ai, 2025), and the models are described as responding to the language of the prompt for text output. However, image generation behavior with mixed-language prompts is undocumented.

For strings like "południe — neutralne" (Polish, meaning "noon — neutral") injected into an English prompt: no primary source confirms degradation. However, all official prompting guides emphasize that the model works best with "descriptive narrative" rather than labeled key-value pairs. A Polish label next to an English value creates an ambiguous key-value fragment that is not idiomatic in either language as a narrative sentence.

**Finding:** Unknown whether Polish strings cause measurable image quality degradation on their own. The more significant issue is the key-value fragment format rather than the language itself. Replacing `"time of day: południe — neutralne"` with a narrative sentence in any single language is the appropriate fix regardless of language choice.

---

## Known quirks

- **[2026-10-20] [ai.google.dev changelog] NB2.1 GA 2026-10-06; NB2 deprecated same day.** Preview IDs (`*-preview`) for 3.1 Flash and Pro were shut down 2026-06-25.

- **[2026-10-06] [Fuser, N=1] NB2.1 did not hit a requested hex glaze (#1F6F5C)** — darker, greyer, slightly yellower; tied with FLUX.2 pro.

- **[2026-10-20] [Gemini API pages] No seed/temperature/system-instruction documentation on image-model pages.** See Reproducibility.

- **[2025-08] [Google Developers Blog, launch post] Acknowledged weak areas at launch:** long-form text rendering, character consistency across unrelated scenes, and factual fine detail in images. Text rendering improved in subsequent models but remains below GPT-Image-1 for precision.

- **[2025-11-04] [Google changelog] Input image token cost cut for `gemini-2.5-flash-image`:** Dropped from 1,290 to 258 tokens per input image, significantly reducing the cost of image editing and reference workflows. This change was not broadly announced; discovered via changelog inspection.

- **[2026-01] [community, `googleapis/python-genai` GitHub issue #1534] `number_of_images` not implemented in Python SDK for Nano Banana models:** Documentation says up to 10 output images per prompt are supported, but the SDK rejects the parameter. No ETA on fix. Imagen 4 (`generate_images()` call) supports this parameter correctly (Imagen 4 shut down 2026-08-17).

- **[2026-02] [community, Google AI Developers Forum] High peak-hour failure rates:** During 9 AM–5 PM Pacific, generation failure rates reported at ~30% for `gemini-2.5-flash-image` and ~45% for `gemini-3-pro-image-preview` (more compute-intensive). Imagen 4 had ~15% failure rate in same window. These are community estimates, not Google SLA figures.

- **[2026-02] [Google changelog] `gemini-3.1-flash-image-preview` launched February 26, 2026** under the "Nano Banana 2" codename. Adds 4K output, thinking, Google Search grounding, and up to 14 reference images.

- **[2026-02-26] [Vertex AI docs] Thinking on by default for `gemini-3.1-flash-image-preview` and `gemini-3-pro-image-preview`.** Cannot be fully disabled on Pro tier per third-party reporting (not independently confirmed against official docs in this pass). Adds latency and billing overhead on complex prompts. (2026-10-20: Gemini API image guide confirms "cannot be disabled in the API" for all Gemini 3 image models.)

- **[2026-03] [community, multiple sources] Transparent background is unsupported across all Nano Banana models.** Output is always on a solid or rendered background. Workaround: prompt for a flat neutral-color background and run through a background removal tool (e.g., rembg) post-generation.

- **[2026-04] [philschmid.de product photography guide] Multi-image lighting mismatch requires explicit instruction.** When compositing a reference object into a new scene, the model does not automatically match shadow direction or light color temperature. Explicit prompting ("ensure the shadow falls to the right at 45 degrees matching the key light position") is required for acceptable results.

- **[2026-05] [community analysis, multiple sources] Identity drift in multi-turn edits.** Fine features (stitching patterns, small logo details, leg joinery) drift between edit turns even when the original reference is re-attached. Workaround: save intermediate "good" outputs and re-feed them as the new base reference rather than running long edit chains from the original.

- **[2026-05] [Vertex AI docs] `gemini-2.5-flash-image` max output images per prompt listed as 10**, but this appears to be a ceiling on what the model could produce if prompted to generate a grid or series, not a `number_of_images` parameter that works reliably. In practice, each call returns 1 image unless the prompt explicitly asks for multiple and the SDK supports it (which it currently does not via `number_of_images`).

- **[source unclear, reported by third parties] Thinking tokens on failed generations:** On `gemini-3-pro-image-preview`, if a generation attempt fails a safety check, thinking tokens are billed even though no image is returned. Estimated cost $0.002–$0.006 per failed attempt. Not confirmed against official billing docs.

- **[2025-12] [community, Google AI Developers Forum] Nano Banana Pro ignores reference images and prompt 10–20% of the time.** Multiple developers independently confirm complete ignores (not subtle drift). Workaround: retry with identical inputs; near-100% success rate on second attempt. Some pipelines add a secondary model verification step before delivering output. Source: discuss.ai.google.dev thread "nano-banan-pro-ignoring-prompt-and-reference-images".

- **[2025-11] [Max Woolf / minimaxir.com] Capitalized "MUST" improves adherence.** Community testing found CAPS on critical instructions and use of "MUST" language measurably improves compliance with specific constraints vs. lowercase phrasing. Source: minimaxir.com/2025/11/nano-banana-prompts/.

- **[2025-11] [Max Woolf / minimaxir.com] "Pulitzer-prize-winning cover photo" style anchors improve composition.** Appending professional-photography context descriptors ("shot for the cover of Wallpaper magazine") improves overall composition and subject framing. This is a style-level anchor, not an environment-level fix.

---

## Failure modes for furniture product photography

- **Leg geometry morphing across variants** — When using a reference leg image alongside a base sofa, the model sometimes blends leg style rather than replacing cleanly: e.g., a hairpin leg gains unnecessary taper, or a tapered leg picks up a spur from a nearby style. Mitigation: use a single, unambiguous leg reference image per call; describe the leg style explicitly in text too ("four tapered cylindrical legs, no braces, no brackets"); specify exact leg count ("four legs, one at each corner").

- **Shadow direction inconsistency** — Generated shadows for swapped elements (legs, cushions, backgrounds) often do not match the original shadow angle in the base photo. Mitigation: state shadow direction explicitly in the prompt ("soft shadow falling to the right at approximately 4 o'clock, matching the existing room light source"); consider post-processing shadow layer rather than relying on generation.

- **Fabric warping at seams and edges** — Upholstery recoloring or material-swap prompts sometimes introduce subtle warp artifacts at piping, stitching lines, and cushion edge seams. Most visible on tufted or welted seam styles. Mitigation: include "preserve all stitching, piping, and seam geometry exactly" in the preserve list; for high-fidelity results, use `gemini-3-pro-image` which shows better seam preservation than the Flash tier.

- **Camera angle drift in long batches** — On multi-turn or high-volume batch runs, camera angle shifts by a few degrees even when the base reference image is re-attached. Mitigation: state angle explicitly in every prompt ("three-quarter front view, approximately 35-degree angle from the left"); use the sofa schema's `camera` field as a prompt element; re-verify angle on every Nth output during long batches.

- **Implicit product redesign** — The model "improves" products unprompted: adds decorative throw pillows, changes proportions to look more editorial, rounds corners, or alters cushion count. This is the most common failure mode. Mitigation: explicit preserve list every call (frame geometry, cushion count, seat depth, arm height, leg count, leg position); phrase as "do not change [list]" in addition to the positive description.

- **Background bleed on transparent-background inputs** — If a product photo has had its background removed (PNG with alpha) before being passed as a reference, the model sometimes reconstructs an incorrect background from training priors (generic white studio, wood floor, etc.) rather than treating the alpha as "no background." Mitigation: flatten alpha to 18% neutral grey before passing as reference (matches the leg library background standard), or pass an explicit background context image.

- **Text in scene ignored or hallucinated** — Brand name or price tags visible in the reference image are frequently distorted or replaced with hallucinated text. Mitigation: if the reference contains text, crop or mask it before passing; do not rely on the model to faithfully reproduce printed text from a reference image.

- **Reference caps** — `gemini-2.5-flash-image` allows 3 refs (legacy). NB2.1/NB2 list 14 total (10 objects + 4 characters inferred); Pro 14 total (6 objects / 5 characters / 3 style); Lite not optimised for multiple refs.

- **Scene/environment ignored when "Neutral studio backdrop" appears earlier in prompt** — Documented as a structural failure: a hardcoded studio-mode line early in the prompt anchors the output mode before the environment description is read. The environment description, especially if in a pipe-delimited notes blob at the end, will be partially or fully overridden. Mitigation: (a) remove any hardcoded backdrop line from the static prompt template; (b) make the scene/environment block the primary scene-setting element, placed in the third structural position (after product identification and preserve list); (c) express environment as a narrative sentence, not a key-value fragment; (d) for lifestyle renders, include lighting type, floor material, wall finish, and color temperature explicitly.

- **[2026-10-20] Colour drift from a requested hex** — Fuser (N=1, 2026-10-06) measured a ceramic glaze off target on NB2.1; thematerialbrief (2025-09) reports solid-colour recolouring works but multi-colour pattern recolouring does not. Mitigation reported by community: verify against a swatch/measured value after generation.

- **[2026-10-20] Fabric pattern scale** — thematerialbrief (2025-09): swatch + blank 3D model gave oversized, distorted pattern; scale was correct when fabric was already applied to a model. Mitigation reported: start from real inputs, use precise textile terminology, expect several iterations.

---

## Competitor positioning (product photography use cases)

**Seedream v4/5 (ByteDance):** Strongest for photorealistic material rendering (leather grain, woven fabric, metal brushing). Supports example-based style transfer ("apply the same change from image A→B to image C"). Weaker on multi-turn conversational editing. No free API tier.

**FLUX Kontext (Black Forest Labs):** Best photorealism for catalog-style images; often indistinguishable from studio photography. Supports in-context editing with high geometric consistency. Open-weight availability enables self-hosting. Weaker on text rendering and semantic instruction following compared to Gemini models. (2026-10: Fuser reports FLUX.2 pro and NB2.1 tied on a hex-colour test, N=1; FLUX.2 documents hex-code prompting.)

**Qwen Image Edit (Alibaba):** Best-in-class for multilingual text rendering within images. Strong on multi-angle consistency from a single reference. Less competitive on Western furniture aesthetics and photorealism of soft furnishings.

**GPT-Image-1 / GPT-Image-2 (OpenAI):** Top performer for precise in-image text rendering and metallic surface accuracy. Strong semantic instruction following. No batch pricing tier as of this pass; no transparent-background support either. Per-image cost competitive with Gemini Flash but higher than FLUX.

**Nano Banana positioning:** Best value for iterative editing workflows (multi-turn with thought signatures, natural-language edits, no mask required). NB2.1 halves 1K/2K price vs NB2 (official pricing page), keeping 14-ref capacity. Pro remains Google's "premium" tier at ~4x NB2.1's 1K price. Thinking cannot be disabled and adds latency/cost.

---

## Sources consulted this pass

2026-10-20 pass (all accessed 2026-10-20):

- https://ai.google.dev/gemini-api/docs/image-generation — 2026-10-20 (first ~100k of 174k chars read in full; tail partially read; guide has templates, no dedicated best-practices section)
- https://ai.google.dev/gemini-api/docs/pricing — 2026-10-20
- https://ai.google.dev/gemini-api/docs/deprecations — 2026-10-20 (two fetches; 2.5 Flash Image row = 2027-03-15)
- https://ai.google.dev/gemini-api/docs/changelog — 2026-10-20
- https://ai.google.dev/gemini-api/docs/models/gemini-nano-banana-2.1 — 2026-10-20
- https://ai.google.dev/gemini-api/docs/models/gemini-3-pro-image — 2026-10-20
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/gemini-image-generation-best-practices — 2026-10-20 (front part of page truncated by fetch tool)
- https://blog.google/products-and-platforms/products/gemini/prompting-tips-nano-banana-pro/ — 2026-10-20
- https://developers.googleblog.com/en/how-to-prompt-gemini-2-5-flash-image-generation-for-the-best-results/ — 2026-10-20
- https://deepmind.google/models/gemini-image/prompt-guide/ — 2026-10-20
- https://fuser.studio/articles/flux-2-vs-nano-banana — 2026-10-20 (community/vendor)
- https://fuser.studio/articles/nano-banana-prompt-guide — 2026-10-20 (community/vendor)
- https://www.promptzone.com/drewgrant/nano-banana-21-prompts-real-examples-and-model-guide-4k4p — 2026-10-20 (community)
- https://runware.ai/docs/models/google-nano-banana-2-1/guides/multi-reference-composition — 2026-10-20 (vendor docs)
- https://thematerialbrief.beehiiv.com/p/i-tested-google-s-nano-banana-ai-on-fabrics — 2026-10-20 (community, article dated 2025-09-11)
- https://minimaxir.com/2025/11/nano-banana-prompts/ — 2026-10-20 (community, 2025-11)
- Search-result summaries only (not opened): decrypt.co/380257/google-launches-nano-banana-2-1, neowin.net NB2.1 launch, digitalapplied.com 2.5 Flash Image retirement post (2026-09-25), human-ai-human.org JSON prompting, prompt-architects.com seeds post, morphic.com / glbgpt.com reference-limit listings, discuss.ai.google.dev seed non-determinism thread (gemini-2.5-pro text model).
- Fetch failures: cloud.google.com ultimate prompting guide (stream aborted), ud.hk NB2.1 consistency article (truncated).

Earlier passes:

- [Models | Gemini API | Google AI for Developers](https://ai.google.dev/gemini-api/docs/models) — 2026-05-08
- [Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing) — 2026-05-11
- [Nano Banana image generation docs](https://ai.google.dev/gemini-api/docs/image-generation) — 2026-05-11
- [Gemini 2.5 Flash Image | Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash-image) — 2026-05-08
- [Gemini 3.1 Flash Image | Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-1-flash-image) — 2026-05-08
- [Gemini 3 Pro Image | Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-pro-image) — 2026-05-11
- [Gemini image generation limitations | Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/gemini-image-generation-limitations) — 2026-05-08
- [Gemini image generation best practices | Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/gemini-image-generation-best-practices) — 2026-05-11
- [Gemini 3 prompting guide | Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/gemini-3-prompting-guide) — 2026-05-11
- [Gemini deprecations | Gemini API](https://ai.google.dev/gemini-api/docs/deprecations) — 2026-05-08
- [Release notes | Gemini API changelog](https://ai.google.dev/gemini-api/docs/changelog) — 2026-05-08
- [Introducing Gemini 2.5 Flash Image — Google Developers Blog](https://developers.googleblog.com/en/introducing-gemini-2-5-flash-image/) — 2026-05-08
- [How to prompt Gemini 2.5 Flash Image — Google Developers Blog](https://developers.googleblog.com/en/how-to-prompt-gemini-2-5-flash-image-generation-for-the-best-results/) — 2026-05-11
- [Nano Banana Pro prompt tips — Google Blog](https://blog.google/products-and-platforms/products/gemini/prompting-tips-nano-banana-pro/) — 2026-05-11
- [Ultimate prompting guide for Nano Banana — Google Cloud Blog](https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-nano-banana) — 2026-05-11
- [How to create effective image prompts — Google DeepMind](https://deepmind.google/models/gemini-image/prompt-guide/) — 2026-05-11
- [Nano Banana can be prompt engineered for nuanced results — minimaxir.com](https://minimaxir.com/2025/11/nano-banana-prompts/) — 2026-05-11
- [Nano Banana Pro ignoring prompt and reference images — Google AI Developers Forum](https://discuss.ai.google.dev/t/nano-banan-pro-ignoring-prompt-and-reference-images/112781) — 2026-05-11
- [Gemini 2.5 Flash Image now ready for production — Google Developers Blog](https://developers.googleblog.com/gemini-2-5-flash-image-now-ready-for-production-with-new-aspect-ratios/) — 2026-05-08
- [Google Gen AI Python SDK docs](https://googleapis.github.io/python-genai/) — 2026-05-08
- [GitHub issue #1534: number_of_images for gemini-2.5-flash-image](https://github.com/googleapis/python-genai/issues/1534) — 2026-05-08
- [The 10 Steps for product AI generation with Gemini 2.5 Flash — philschmid.de](https://www.philschmid.de/gemini-image-generation-product) — 2026-05-08
- [Seedream 5.0 vs Nano Banana Pro vs GPT Image 1.5 vs Flux Klein vs Qwen Image — WaveSpeedAI](https://wavespeed.ai/blog/posts/seedream-5-0-vs-nano-banana-pro-gpt-image-flux-klein-qwen-image-comparison-2026/) — 2026-05-08
- [Gemini 3.1 Flash Image Preview pricing — aifreeapi.com](https://www.aifreeapi.com/en/posts/gemini-flash-image-generation-pricing) — 2026-05-08
- [Gemini 2.5 Flash Image replacement — aifreeapi.com](https://www.aifreeapi.com/en/posts/gemini-2-5-flash-image-replacement) — 2026-05-08
- [Gemini 3 Pro Image pricing — Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/pricing) — 2026-05-11
- [Gemini image generation limitations — Gemini Enterprise Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/gemini-image-generation-limitations) — 2026-05-08 (page did not return full content)

---

## Changelog

### 2026-05-08 — Initial pass

First research pass. No prior version of this document existed. Key findings established:

- Three active Nano Banana model IDs confirmed with GA/preview status and pricing.
- `gemini-2.5-flash-image-preview` confirmed shut down January 15, 2026.
- `gemini-2.5-flash-image` scheduled for deprecation October 2, 2026.
- `number_of_images` SDK bug documented (GitHub issue #1534, unresolved).
- Input image token cost reduction (1,290 → 258 tokens) for `gemini-2.5-flash-image` confirmed via changelog, November 4, 2025.
- System instruction support confirmed for all three active models per Vertex AI capability tables.
- Thinking tokens on by default for 3.1 Flash Image and Pro image; cannot be fully disabled on Pro.
- Transparent background output confirmed unsupported across all models.
- Competitor positioning established vs. Seedream, FLUX Kontext, Qwen Image Edit, GPT-Image-1.
- Seven furniture product photography failure modes documented with mitigations.

### 2026-05-11 — Scene adherence pass

Focused research triggered by reported scene/environment adherence failure in Nano Sofa Studio. No model lineup or pricing changes found since 2026-05-08 pass. Key findings added:

- New "Scene/environment adherence" section added with five sub-findings covering: prompt ordering, instruction conflict behavior, notes-blob under-weighting, text-only vs reference image for scene, and Polish-language mixing.
- Architecture implication #6 added: the `generator.py` structure (hardcoded studio line early, environment in trailing notes blob) is confirmed to conflict with documented Gemini prompt processing behavior in two independent ways (early-anchor bias, first-match-stops-processing).
- Two new quirks added: reference image ignore rate (10–20%, Google AI Developers Forum, Dec 2025) and CAPS/"MUST" adherence improvement (minimaxir.com, Nov 2025).
- New failure mode added: "Scene/environment ignored when Neutral studio backdrop appears earlier in prompt."
- Pricing verified against official page — no changes from 2026-05-08 pass.

### 2026-08-27 — Official-docs update

Image-generation guide updated 2026-08-26: stable IDs `gemini-3.1-flash-image` and `gemini-3-pro-image` replaced the `-preview` IDs.

### 2026-10-20 — Model-lineup, prompting-guidance and reproducibility refresh

Changed since 2026-08-27:

- **New model:** `gemini-nano-banana-2.1` GA 2026-10-06 ($0.0336 / $0.0504 / $0.113 per 1K / 2K / 4K; batch half). `gemini-3.1-flash-image` deprecated same day (no shutdown date). New `gemini-3.1-flash-lite-image` (GA 2026-06-30, 1K only, $0.0336).
- **Preview IDs shut down** 2026-06-25; Imagen 4 shut down 2026-08-17 (removes the `number_of_images` workaround).
- **`gemini-2.5-flash-image` shutdown date conflict:** deprecations page 2027-03-15 vs pricing page text 2026-10-02. Flagged, unresolved.
- Pro `gemini-3-pro-image` is stable; image input is 560 tokens (cost_tracker uses 258).
- Reference-limit breakdown by type added (inferred from a flattened table; Pro corroborated by third parties; NB2 object count conflicts with Morphic's 14).
- Official prompting guidance compiled (material, colour, camera, references, background, negatives); explicit gaps recorded: no official guidance on HEX codes, colour-patch references, reference order, max refs for reliable adherence, or JSON prompts.
- Reproducibility: no documented seed/temperature for image models; thinking cannot be disabled; `thinking_level` options recorded.
- Practitioner findings added (Fuser hex test, thematerialbrief fabric test, promptzone, Runware). No source found for framing collapse, flat colour-patch references, or velvet stereotype.
- Pipeline-vs-guidance contradictions listed at top and in the 2026-10-20 section.
- Pricing re-verified against the official page this pass (3 of 5 models changed or are new; 3.1 Flash and Pro prices unchanged from May).
