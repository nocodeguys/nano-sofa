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
- `/help` → `frontend/help.html` — user guide (`src/help.js`)
- `/docs` → FastAPI Swagger UI

## Files

- `server.py` — FastAPI: serves the built frontend + `/api/*` (generate, generate-set, variants, video, history, config)
- `catalog.json` — single source of truth for materials + colours (PL display + EN prompt specs); served to the browser as `window.NS_CATALOG` via `GET /catalog.js`
- `frontend/src/data.jsx` — option tables shared by the pages (builds COLORS/MATERIALS from the catalog)
- `frontend/src/styles-v2.css` — design system (sage accent, Geist)
- `scene-references/` — curated per-environment reference images (baked into the image)
- `requirements.txt` — Python runtime deps (what the Docker image installs)

Cache busting is automatic: Vite hashes asset filenames; `/catalog.js` is
`Cache-Control: no-store`.
