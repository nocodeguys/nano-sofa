# app-v2 — Nano Sofa Studio (design port)

Alternative UI to the Gradio app under `app/`. Ported from the Claude Design
prototype (`Nano Sofa Studio.html` + companion `.jsx`/`.css`). Reuses
`app/core/generator.py` for the actual API call.

## Run

```bash
./app-v2/run.sh
# → http://localhost:7861
```

The script installs FastAPI/uvicorn into the project venv and starts the server
on port 7861 (override with `PORT=...`).

## What's wired

- 7-step wizard from the prototype: photo, color, material, size, legs, scene, refs
- Real file upload on step 01 (drag-drop or click)
- Real Gemini API key field in the topbar (stored in `localStorage` only)
- Generuj wariant → `POST /api/generate` → `app.core.generator.generate()` → real PNG
- Returned image renders in the live preview stage and in the gallery dock

## What's stub-only (matches v1 scope, lift if needed)

- Reference image slots (step 07) — UI present, not sent to backend
- Tabs other than "Generuj" (Porównaj, Koszty, Schemat) — header pills only
- Cost dock value — derived client-side, not from `cost_tracker`

## Files

- `Nano Sofa Studio.html` · `app.jsx` · `steps.jsx` · `data.jsx` · `styles.css` — prototype, lightly modified
- `server.py` — FastAPI: serves prototype, exposes `/api/generate`, `/api/outputs/<file>`
- `requirements.txt` — additive deps over the v1 requirements
- `run.sh` — convenience launcher
