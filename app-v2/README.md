# app-v2 — Nano Sofa Studio

The app Docker runs: FastAPI backend (`server.py`) + a Vite-built React UI.
Reuses `app/core/` (generator, cost tracker, schema loader) for the actual
Gemini calls.

## Run

```bash
./app-v2/run.sh
# → http://localhost:7861
```

The script installs FastAPI/uvicorn into the project venv, builds the frontend
once if `frontend/dist` is missing, and starts the server on port 7861
(override with `PORT=...`).

### Catalogue admin

Open [http://localhost:7861/admin](http://localhost:7861/admin) or choose
**Katalog** in the top menu. The panel edits the Polish labels and English
prompt descriptions for fabrics, manages canonical texture-reference images,
and edits or adds colours (name, HEX, covered swatches and model description).

**Zapisz i przebuduj** validates the data and images, runs a Vite build in a
staging directory, snapshots the previous version, promotes the new files and
reloads the stable in-memory catalogue mappings used by the running backend.
If any step fails, the previous working version is restored. The latest 10
snapshots live under `outputs/catalog-backups/`. The admin page and API are
restricted to localhost.

## Frontend dev loop

```bash
./app-v2/run.sh              # terminal 1 — API on :7861
cd app-v2/frontend && npm run dev   # terminal 2 — Vite HMR on :5173, proxies /api
```

For a production check: `npm run build` in `app-v2/frontend`, then restart the
server (it serves `frontend/dist`).

## Pages

- `/` → `frontend/index.html` — main configurator (`src/app-v2.jsx`)
- `/video` → `frontend/video.html` — video studio (`src/video.jsx`)
- `/editorial` → `frontend/editorial.html` — freeform editorial shots, no base photo (`src/editorial.jsx`)
- `/admin` → `frontend/admin.html` — local catalogue administration (`src/admin.jsx`)
- `/help` → `frontend/help.html` — user guide (`src/help.js`)
- `/docs` → FastAPI Swagger UI

## Files

- `server.py` — FastAPI: serves the built frontend + `/api/*` (generate, generate-set, variants, video, history, config)
- `studio/normalize.py` — deterministic packshot normalization (see below)
- `catalog.json` — single source of truth for materials + colours (PL display + EN prompt specs); served to the browser as `window.NS_CATALOG` via `GET /catalog.js`
- `frontend/src/data.jsx` — option tables shared by the pages (builds COLORS/MATERIALS from the catalog)
- `frontend/src/styles-v2.css` — design system (sage accent, Geist)
- `scene-references/` — curated per-environment reference images (baked into the image)
- `requirements.txt` — Python runtime deps (what the Docker image installs)

## Catalog profile

The v3 configurator exposes two mutually exclusive workflows. **Katalog** sends
only product choices, profile and yaw; the profile owns the backdrop, light,
lens, aperture and camera height. **Lifestyle / wnętrze** exposes and sends the
environment, camera and extra references instead. Hidden controls are omitted
from the request rather than merely losing an override contest in the backend.

A product grid only reads as one photo session if the backdrop, the subject
scale and the floor line are identical on every tile. Three layers get it
there, all enabled by the section-01b "Profil katalogowy" toggle (`catalog=1`
on `/api/generate` and `/api/generate-set`):

1. **Locked settings** (`_CATALOG_LOCKS` + `_CATALOG_PROFILE_ENV` in
   `studio/mappings.py`) — 85 mm, f/8, eye-level camera, plus one of three
   backdrops picked with `catalog_profile`:

   | id | tone | look |
   |----|------|------|
   | `ivory` (default) | #F7F5F1 | restrained neutral architectural ivory, without a yellow cast |
   | `atelier` | #A8A292 → #EEE7E7 | two-axis lit cyclorama measured from the supplied studio reference: olive-grey upper-left opening into pale dusty blush lower-right, with fixed fine grain |
   | `softblush` | #FAF8F6 | calm blush-cream field measured from the supplied bed-catalog reference; constant tone, depth carried only by the product shadow |
   | `paperwhite` | #FCFAF7 | bright airy off-white, barely any gradient |
   | `neutral` | #FAFAFA | clinical photo-studio white, for marketplaces that composite onto their own background |

   Each id names both a cyclorama prompt profile and the `PackshotProfile` of
   the same name in `studio/normalize.py`; keeping the two in step is what
   lets normalization be a nudge rather than a repaint. Yaw stays with the
   user — which way a product faces is a real per-product choice, unlike the
   backdrop.
2. **Numeric framing contract** (`_CATALOG_FRAMING_CONTRACT`) — subject width,
   centring and floor-contact height as percentages of the frame. The
   qualitative framing strings ("breathing room above and below") are read
   differently for a low platform bed than for a tall continental one, which
   is what makes a grid look like eight separate shoots.
3. **Safe photographic calibration** (`studio/normalize.py`) — the brand-facing
   pale profiles estimate a fixed low-frequency studio field, then replace only
   smooth backdrop pixels connected to the frame with the clean canonical plate.
   This removes halos, stains and compression artifacts inherited from weak source
   references. Product and uncertain integration pixels receive a tightly limited
   colour nudge, preserving
   pale bouclé, white bedding and the natural contact shadow without a semantic
   cut-out or synthetic ellipse. The neutral marketplace profile retains the
   stricter matte/rescale path where contrast is sufficient. Frame edges are
   corrected as part of the same continuous low-frequency field — they are not
   replaced with hard strips, which avoids visible horizontal exposure bands.

   Every brand profile also has a curated empty-studio image in
   `scene-references/`. It is attached automatically before generation, while
   section-07 uploads and moodboard scene locks are ignored in catalog mode.
   The prompt therefore starts from the same studio plate and the finishing
   pass removes the remaining low-frequency colour drift without damaging the
   product. Canonical material close-ups are assigned a separate texture-only
   role and explicitly forbidden from affecting bedding, shadows or the studio
   plate, preventing enlarged bouclé loops from leaking onto the backdrop.

Optionally pass `anchor_ref` (a generation id or an output basename) to make an
approved earlier render the authority for camera, lighting and backdrop, so
product #40 matches product #1 rather than merely obeying the same written
spec.

The strict neutral-profile matte refuses renders it should not touch — lifestyle
scenes, macro crops, anything where the product bleeds off the frame edge — and
logs why. Every profile keeps the pre-normalization render beside the master as
`<stem>.raw.png`.

Cache busting is automatic: Vite hashes asset filenames; `/catalog.js` is
`Cache-Control: no-store`.
