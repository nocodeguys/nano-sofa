# app-v2 — Nano Sofa Studio

The app Docker runs: FastAPI backend (`server.py`) + static React UI compiled
in the browser. Reuses `app/core/` (generator, cost tracker, schema loader)
for the actual Gemini calls.

## Run

```bash
./app-v2/run.sh
# → http://localhost:7861
```

The script installs FastAPI/uvicorn into the project venv and starts the server
on port 7861 (override with `PORT=...`).

## Pages

- `/` → `Nano Sofa Studio v2.html` — main configurator (`app-v2.jsx` + `tweaks-panel.jsx` + `header.jsx`)
- `/video` → `video.html` — video studio (`video.jsx`)
- `/help` → `docs.html` — user guide
- `/docs` → FastAPI Swagger UI

## Files

- `server.py` — FastAPI: static serving + `/api/*` (generate, generate-set, variants, video, history, config)
- `data.jsx` — product / material / color / camera data shared by the pages
- `styles-v2.css` — design system (sage accent, Geist)
- `requirements.txt` — runtime deps (this is what the Docker image installs)
- `run.sh` — convenience launcher

Cache busting: static assets are referenced with `?v=YYYYMMDDx` query strings
in the HTML — bump them when you change an asset, or Watchtower-updated
clients keep the stale cached copy.
