# Nano Sofa Studio

AI-powered product photography for upholstered furniture. Upload a base sofa or bed photo, pick a color and fabric, choose a scene — get a publishable variant in ~12 seconds. Polish UI, runs locally in Docker, no Python/Node install required.

Built on Google's Gemini image models (2.5 Flash + the new 3.1 Flash / 3 Pro previews).

```
┌────────────────────────────┬──────────────────────────────────┐
│  Live preview (sticky)     │  Single-page configurator        │
│  • sofa color / fabric     │  01 model / aspect / resolution  │
│  • size / camera / scene   │  02 base photo + type            │
│  • generated PNG renders   │  03 color · 12 fabric swatches   │
│                            │  04 material · bouclé / aksamit  │
│  [ Generuj wariant ⌘↵ ]    │  05 size · 1–4 seater / L / U    │
│                            │  ...                              │
└────────────────────────────┴──────────────────────────────────┘
```

## Quick start

**Run with Docker** (Docker Desktop required):

```bash
docker run --rm -p 7861:7861 -v "$PWD/outputs:/app/outputs" \
  ghcr.io/nocodeguys/nano-sofa:latest
```

Then open <http://localhost:7861>, paste your Gemini API key (get one at <https://aistudio.google.com/app/apikey>), and click **Generuj wariant**.

**Or with compose** — download `docker-compose.yml` + `install/` from this repo, then:

```bash
docker compose up
```

**Non-technical teammates:** download the install bundle, then double-click `install/start-mac.command` (Mac) or `install/start-windows.bat` (Windows). The script handles "Docker not installed" / "Docker not running" cases gracefully.

See [`INSTALL.md`](INSTALL.md) for the full end-user guide and troubleshooting.

## What it does

- **Upload** a base product photo (JPG/PNG/WEBP, ≥ 1024 px)
- **Configure** color (12 fabric swatches or custom), material (bouclé / aksamit / len / szenila / skóra / tkanina płaska), size (1–4 seater, L/U sectional, single→king bed), legs (preserve or swap to one of 5 styles), camera + scene + lighting, optional reference images
- **Generate** — Gemini returns a photorealistic variant matching the base product's frame and proportions

The API key never leaves your browser session (stored in `localStorage`, sent only as a form field on each generate call). No telemetry, no analytics, no server-side key storage.

## Supported models

The model picker reads from `prompts/schemas/sofa.json` at startup, so adding a new model is a schema edit, not a code change.

| Model | Tier | Max refs | Max resolution |
|---|---|---|---|
| `gemini-2.5-flash-image` | flash | 3 | 1K |
| `gemini-3.1-flash-image-preview` | flash | 14 | 4K |
| `gemini-3-pro-image-preview` | pro | 14 | 4K |

The UI disables resolution/ref-count options that the active model doesn't support.

## Local development (without Docker)

```bash
git clone https://github.com/nocodeguys/nano-sofa.git
cd nano-sofa
python3 -m venv .venv && source .venv/bin/activate
pip install -r app-v2/requirements.txt
python app-v2/server.py
# → http://localhost:7861
```

Hot-reload during UI work: the React prototype loads through `@babel/standalone` from CDN, so editing `app-v2/*.jsx` and refreshing the browser is the whole loop. No build step.

### Environment variables

| Var | Default | Purpose |
|---|---|---|
| `PORT` | `7861` | Listen port |
| `HOST` | `0.0.0.0` | Listen host |
| `OUTPUTS_DIR` | `<repo>/outputs` | Where renders + uploads land. **Bind-mount this** in Docker so renders persist. |
| `LOG_LEVEL` | `info` | uvicorn log level |

No `GEMINI_API_KEY` env var — keys come from the browser UI, per user.

## Repository layout

```
app/                     # Shared core (generator, cost tracker, schema loader)
  core/generator.py      # Prompt assembly, retry, alpha-flatten, multi-turn history
  core/cost_tracker.py   # Per-request cost logging (SQLite, ephemeral in container)
  core/schema_loader.py  # Reads prompts/schemas/sofa.json, exposes typed helpers
app-v2/                  # FastAPI server + React UI (this is what Docker runs)
  server.py              # Entry point: GET /, /v1, /healthz, /api/config, POST /api/generate
  app-v2.jsx             # Main app shell — 3-pane configurator
  steps.jsx, data.jsx    # Wizard steps + product/material/color/camera data
  styles-v2.css          # Calm composer design (sage accent, Instrument Serif + Geist)
  Nano Sofa Studio v2.html  # Entry HTML (loads JSX through Babel standalone)
prompts/schemas/         # JSON schemas — source of truth for model constraints
prompts/test-matrices/   # Eval matrices (per schema)
legs/                    # 3D leg reference library + manifest
docs/research/           # Nano Banana model state, refreshed by the researcher agent
.claude/agents/          # Subagent definitions (one per concern)
.github/workflows/       # CI: multi-arch Docker build → GHCR
Dockerfile               # Multi-stage, ~459 MB, non-root user, healthcheck
docker-compose.yml       # Single service, single volume (./outputs)
install/                 # Double-click launchers (start-mac.command + start-windows.bat)
INSTALL.md               # Non-technical install guide
```

## Endpoints

| Route | Purpose |
|---|---|
| `GET /` | v2 design (current) |
| `GET /v1` | Earlier design, preserved as static HTML |
| `GET /healthz` | Liveness + model catalogue. No external calls. Used by Docker `HEALTHCHECK`. |
| `GET /api/config` | Model enum + per-model constraints (driven by `prompts/schemas/sofa.json`) |
| `POST /api/generate` | Run one generation. Form fields: `api_key`, `kind`, `color`, `mat`, `size`, `legs`, `cam`, `lens`, `tod`, `shadow`, `env`, `model`, `aspect`, `res`, `seed`, `base_image` |
| `GET /api/outputs/<file>` | Serve a generated PNG |

## Status

- **v2 (current):** Production-shaped. Docker image published to GHCR. Three Gemini models exposed through the picker. Phases 1–3 complete: dynamic model picker, API key onboarding, env-configurable runtime, multi-arch image, double-click installers.
- **v1 (earlier Gradio UI):** kept at the `/v1` static route for reference. Its Python entry point (`app/main.py`) is intentionally not part of the v2 image.

## How the agent system works

Each agent under `.claude/agents/` owns one concern:

- `nano-banana-researcher` → `docs/research/nano-banana-state.md`
- `furniture-prompt-architect` → `prompts/schemas/*.json`
- `leg-pipeline-designer` → `legs/render-blender.py`, leg manifests
- `gradio-app-architect` → previously `app/` (Gradio); now superseded by FastAPI + React in `app-v2/`
- `docker-packager` → `Dockerfile`, `docker-compose.yml`, `install/`, `INSTALL.md`

They share state through files, not chat. The JSON schemas are the contract — the prompt architect's output is what the UI reads at runtime. A non-technical teammate can edit a schema (add a model, change a constraint) without touching code; the change takes effect on the next server restart.

## Roadmap

- [ ] Compare / batch generation panel (UI tab exists, backend pending)
- [ ] Cost tracking volume so history survives container restarts
- [ ] Reference image uploads end-to-end (UI exists, server-side multi-file pending)
- [ ] Bed-specific prompt rules (partially wired — schema branches on `product_type`)
- [ ] GitHub Release workflow that ships a `nano-sofa-vX.Y.Z.zip` install bundle

## License

Project code: see [`LICENSE`](LICENSE) (TBD).
The Gemini model output is governed by Google's usage policies for the model you select.
