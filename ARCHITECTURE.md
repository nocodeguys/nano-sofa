# Architecture — Nano Sofa Studio

Concept + flow + invariants. Read this before touching prompt wording,
material data, or the deploy pipeline. The README covers install/run;
this file covers *why the code is shaped the way it is*.

## What this is

An internal studio for generating **product photos and videos of furniture**
(sofas and beds) with Google Gemini image models ("Nano Banana") and Veo 3.1.
The user picks a base product photo plus parametric variant choices —
color (TreeTale fabric matrix), material, size, legs, scene, camera — and the
app assembles a tightly controlled prompt with reference images, calls Gemini,
and stores the renders. Non-technical teammates run it as a Docker container
that updates itself.

## System shape

```
Browser (React UI, static)          FastAPI (app-v2/server.py)         Shared core (app/core/)
┌─────────────────────────┐  POST   ┌─────────────────────────┐        ┌──────────────────────────┐
│ /       configurator    │ ──────▶ │ /api/generate            │ ─────▶ │ generator.py             │──▶ google-genai
│ /video  video studio    │  form   │ /api/generate-set        │  Gen-  │  prompt assembly, retry, │    (Gemini / Veo)
│ /editorial freeform     │         │ /api/generate-variants   │  Request│  alpha-flatten, history │
│ /help   user guide      │         │ /api/generate-free       │        │ video_generator.py       │
└─────────────────────────┘         │ /api/generate-video      │        │ cost_tracker.py (SQLite) │
        ▲                           │ /api/config, /healthz …  │        │                          │
        │ static files + JSON       └─────────────────────────┘        │ schema_loader.py         │
        └───────────────────────────────────┘                           │ leg_browser.py           │
                                                                        └──────────────────────────┘
Outputs: PNG/JPG → outputs/  (volume-mounted in Docker; EXIF-stamped "Nano Sofa Studio v2")
```

- **API keys are per-user, browser-side.** Stored in `localStorage`, sent with
  each request. The server never holds a `GEMINI_API_KEY`.
- The split is deliberate: `server.py` owns HTTP + translating UI ids into
  English prompt fragments; `app/core/generator.py` owns the model call
  (prompt text assembly, reference-image collection, retries, error taxonomy).

## Flow of one generation

1. UI posts form fields (`kind`, `color`, `mat`, `size`, `legs`, `cam`, `lens`,
   `tod`, `shadow`, `env`, `model`, `aspect`, `res`, `seed`) + `base_image`.
2. `server.py` maps Polish/UI ids → English prompt fragments
   (`_MATERIAL_PL_TO_EN`, `_MATERIAL_TEXTURE_EN`, scene/camera tables) and
   builds a `GenerationRequest` with named reference slots: base product,
   leg reference (from `legs/manifest.json`), scene reference, fabric swatch,
   plus free-form extra refs (capped to the model's `max_refs`).
3. `generator.generate()` assembles the final prompt text, flattens alpha,
   calls Gemini with exponential backoff, classifies failures, saves the
   image, logs cost to SQLite (`app/state/costs.db`).
4. Debugging wording: `NANO_SOFA_LOG_PROMPT=1` dumps the full prompt that
   crossed the wire. Off by default.

**Editorial mode** (`/editorial` → `/api/generate-free`) is the exception to
the flow above: pure text-to-image, no base product slot. The user's brief
leads; optional picker fragments (style from `_EDITORIAL_STYLES`, scene,
light, lens, camera height, TreeTale palette, fabric cue) are appended as
art direction (fabric + palette are hard constraints, people-in-frame picker
defaults to an explicit no-people negative), plus up to 3 moodboard refs.
`GenerationRequest.freeform_prompt` carries the composed text verbatim — the
variant prompt assembly, preserve list, and base-image validation are all
skipped. Editorial is also the only place the OpenRouter engine exists
(`studio/openrouter.py`: FLUX.2 pro, Seedream 4.5 — strong at composing from
scratch, banned from the variant pipeline per the bake-off): same composed
prompt, user's own OpenRouter key (browser-stored, like the Gemini key),
same outputs naming and delivery pipeline.

## Sources of truth

| What | Where | Notes |
|---|---|---|
| Model catalogue + constraints (max refs, resolutions) | `prompts/schemas/sofa.json` | The contract. Editable without code; takes effect on server restart. UI reads it via `/api/config`. |
| Leg reference library | `legs/manifest.json` + renders | See `legs/ADDING-A-LEG.md`. |
| Materials & colors | **currently duplicated in 5 places** — see invariant below | Being consolidated server-side, served via `/api/config`. |
| Model research notes | `docs/research/nano-banana-state.md` | Refreshed by the `nano-banana-researcher` agent. |

## Invariants (hard-won — do not relearn these)

1. **The English material noun outweighs the texture spec.** A bare noun like
   "chenille fabric" pulls the model toward its stereotype (velvet) and
   silently cancels a paragraph of texture description. The noun must agree
   with the spec ("woven textured chenille fabric"). Learned twice:
   plecionka (a794761), szenila (ab1f898).
2. **Materials & colours live in `app-v2/catalog.json`** — the single source
   of truth. `server.py` derives its prompt dicts from it; the browser gets it
   as `window.NS_CATALOG` via `GET /catalog.js` (no-store); the schema enum is
   validated against it at startup. The only thing still hand-synced is the
   `.mat-*` picker *visual* in `styles-v2.css` (keyed by the catalog's `tex`
   field) — keep the visual in agreement with `texture_en` (e.g. no glossy
   sheen sweep on matte fabrics).
3. **Video: never send `person_generation` unless explicitly set** — sending
   it blind caused `INVALID_REQUEST` (9cb5931). Empty string = let the API
   apply its per-mode default.
4. **Fotosesja/variants: no fabric-swatch reference image** — including it
   collapsed the framing (b59b49b).
5. **Cache busting is automatic**: Vite emits hashed asset filenames, so
   Watchtower-updated clients can never run stale JS against a new API.
   The one non-hashed asset is `/catalog.js`, which is served with
   `Cache-Control: no-store` for the same reason.
6. **`/docs` belongs to Swagger**; the user guide lives at `/help`.
7. **Beds vs sofas share one pipeline**: `product_type` switches prompt
   blocks; platform/divan beds set `leg_count=0`.

## Deploy loop

```
edit → commit → push (main) → GitHub Actions (docker.yml):
     tests (prompt invariants + API smoke) → multi-arch image → GHCR
     → Watchtower on user machines pulls it

```

**Local edits are invisible to users until pushed** — there is no other
deploy path. Local dev: `./app-v2/run.sh` (uses `.venv`, port 7861).

## Refactor roadmap (2026-08)

- [x] Remove dead Gradio app + `/v1` static UI (5b2f4c7)
- [x] Single source of truth for materials/colors (`app-v2/catalog.json` + `/catalog.js`)
- [x] Vite build: production React, ES modules, self-hosted fonts, hashed assets
- [x] Split `server.py` into `studio/` modules (paths, catalog, mappings, request_builder, media, routes_*)
- [ ] Split the frontend `App()` (~2300 lines) into components — now easy with ES modules, do it opportunistically as sections get touched
- [x] Prompt-invariant tests (texture spec must survive into the final prompt) + smoke tests gating CI
- [ ] Decide fate of the WebGL 3D preview branch (`worktree-webgl-3d-preview`, 15 commits behind)
