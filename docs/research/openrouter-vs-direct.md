# OpenRouter vs direct Google API — research (2026-08-17)

Question: should nano-sofa route image/video generation through OpenRouter for
more models, better prices, and better stability? Web-verified 2026-08-17;
sources inline. TL;DR: **not as a replacement for Gemini — but valuable as a
second provider unlocking non-Google fallback models.**

## 1. Pricing — the "cheaper" claim is false for Gemini

OpenRouter has **zero markup on inference** (pass-through of provider list
prices — [FAQ](https://openrouter.ai/docs/faq)), so the same Gemini model can
never be cheaper there. The real cost deltas:

| Route | gemini-2.5-flash-image (1K) | gemini-3-pro-image (1K/2K) |
|---|---|---|
| Google direct | $0.039 | $0.134 |
| Google **Batch API** (−50%, not on OpenRouter) | ~$0.020 | $0.067 |
| OpenRouter, credits (+5.5% top-up fee) | $0.041 | $0.141 |
| OpenRouter, BYOK (fee-free under $25k/mo list) | $0.039 | $0.134 |
| fal.ai | $0.039 | $0.15 (+12%) |

Per-image prices derive from official token pricing
([ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing))
and were verified identical in OpenRouter's endpoints API. The only genuinely
cheaper path for bulk renders is Google's own Batch API (50% off) or the flex
tier (~50% off, slower) — both exist on the Google side, not via OpenRouter's
Image API.

## 2. Stability — the reputation doesn't transfer to image models

Every OpenRouter route for the Gemini image family terminates at **Google
itself** (AI Studio and/or Vertex — verified via
`/api/v1/models/{slug}/endpoints`). There is no third-party capacity, so the
well-documented Nano-Banana-Pro overloads (global 503 spikes, 429
`RESOURCE_EXHAUSTED` waves) hit OpenRouter users identically — Adobe told its
users the same thing about their own integration. OpenRouter's stability
reputation was earned on **text** LLMs with many independent upstreams.

What OpenRouter *does* add for Gemini: AI Studio↔Vertex failover on
2.5-flash-image, access to Google's priority tier, **all-or-nothing billing**
(failed generations are not billed), per-request USD cost in the response.

The only strong stability play: **fallback to a non-Google model** (Seedream,
FLUX.2) in the same API when Google is overloaded.

## 3. What OpenRouter actually unlocks — more models, one key

Dedicated Image API (`POST /api/v1/images`, June 2026) with normalized
`resolution` / `aspect_ratio` / `seed` / `output_format`, base64 responses,
and `input_references` (multi-image conditioning). 43 image models live.
Relevant for product photography with reference fidelity:

| Model (slug) | Multi-ref | Per image | Notes |
|---|---|---|---|
| `google/gemini-2.5-flash-image` | **max 3 refs** ⚠ | $0.039 | our default; ref cap is BELOW what we send (base+leg+scene+swatch+extras) |
| `google/gemini-3.1-flash-image` | 14 refs | $0.067 (1K) | |
| `google/gemini-3-pro-image` | 14 refs | $0.134 | |
| `bytedance-seed/seedream-4.5` | 10–14 refs | **$0.04 flat (1K–4K)** | marketed for e-commerce product composites |
| `black-forest-labs/flux.2-pro` | 8–10 refs | ~$0.09 (1K + 4 refs; refs billed as input MP) | strongest Gemini rival |
| `openai/gpt-image-1.5 / gpt-image-2` | 16 refs | $0.03–0.13 by quality | `input_fidelity: high` mode |
| `qwen/qwen-image-3` | 4 refs | $0.03–0.075 | cheapest credible; open weights |

Not listed on OpenRouter: Imagen 4, Ideogram, Stability.

**Auth UX:** same pattern as our Gemini key (user-supplied bearer key,
browser-stored, forwarded per request; CORS open). Bonus: OAuth PKCE flow —
users connect their OpenRouter account with one click instead of pasting a
key. `GET /api/v1/key` exposes remaining credit for the UI.

## 4. Video (Veo) — conflicting findings, verify before relying on it

One research pass found a live async Video API
(`POST /api/v1/videos`, 23 models incl. `google/veo-3.1`/`-fast` at prices
matching Google, image-to-video via `frame_images`); the other found the Veo
endpoints returning **all-zero pricing fields**. Treat OpenRouter-for-Veo as
unverified until a paid test call proves billing behaves; keeping Veo direct
via the Google key is the safe default. Note: OpenRouter video is excluded
from their ZDR guarantees.

## 5. Fit with nano-sofa's architecture

- Our prompt stack (texture specs, cyclorama profiles, noun-vs-spec rules) is
  **tuned to Gemini**. Any alternative model needs a bake-off on our own test
  matrix (`prompts/test-matrices/`) before trusting it with fabric fidelity
  and product geometry. Nobody matches Gemini's documented multi-ref subject
  consistency on paper; quality must be proven empirically.
- The 3-ref cap on `gemini-2.5-flash-image` via OpenRouter is a functional
  regression vs direct for our workflow.
- Post-refactor, adding a provider is cheap: `app/core/generator.py` owns the
  single API call site; a provider adapter (google-genai vs OpenRouter Images
  API) + schema-driven model entries in `prompts/schemas/sofa.json` is all
  that's needed. Per-user keys stay browser-side either way.

## Recommendation

1. **Don't move Gemini traffic to OpenRouter** — price is equal-or-worse,
   stability is identical (same upstream), and the cheap default model loses
   reference slots.
2. **Do add OpenRouter as an optional second provider** for what it's
   actually good at: alternative models. Concretely: Seedream 4.5 ($0.04,
   e-commerce-oriented, 10+ refs) and FLUX.2 pro as (a) fallback when Google
   returns 503/429, (b) bake-off candidates for materials where Nano Banana
   underperforms. One OpenRouter key covers all of them; OAuth onboarding.
3. **First step is a bake-off, not integration**: render the standard test
   matrix (one bed + one sofa, one parameter at a time) on Seedream 4.5 and
   FLUX.2 pro vs current Gemini output. Cost: a few dollars. Only integrate
   if quality survives.
4. For real savings on bulk/batch renders, look at **Google Batch API (−50%)**
   — a bigger lever than any aggregator.

## Flagged as unverified

Veo-on-OpenRouter billing (zeros in endpoints API), Krea pricing, exact
current Google tier rate limits (dashboard-only), head-to-head error-rate
data OpenRouter-vs-direct, "50%-off" reseller sites (avoid — ToS/provenance).
