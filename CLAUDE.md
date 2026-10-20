# CLAUDE.md

**What this is:** Nano Sofa Studio — FastAPI + React app generating furniture product photos/videos with Gemini (Nano Banana / Veo) and OpenRouter/OpenAI image models; shipped as a self-updating Docker image. See `ARCHITECTURE.md` (invariants, generation flow) and `app-v2/README.md` (pages, catalogue admin) before changing prompts, catalogue data or deploy.

## Stack
Python 3.12, FastAPI + uvicorn, google-genai, Pillow, numpy, httpx · React 18 + Vite 6 (Node 22) · pytest · Docker multi-arch → GHCR → Watchtower. UI copy is Polish; prompts are English.

## Commands
- Install: `python3 -m venv .venv && source .venv/bin/activate && pip install -r app-v2/requirements-dev.txt && (cd app-v2/frontend && npm ci)`
- Build frontend (required before the server or tests will even import): `cd app-v2/frontend && npm run build`
- Dev server: `./app-v2/run.sh` (→ :7861; builds dist if missing). Frontend HMR: `cd app-v2/frontend && npm run dev` (:5173, proxies /api to :7861 — start the server first)
- Test: `pytest tests/ -q` (no API keys needed; same gate CI runs)
- Lint: none configured.
- Docker: `docker compose up` (pulls GHCR image) or `docker build -t nano-sofa .`

## Layout
- `app/core/` — shared engine: generator (prompt assembly, ref-slot capping, retry), video, cost tracker
- `app-v2/server.py` + `app-v2/studio/` — FastAPI routes, mappings, catalogue, external engines
- `app-v2/frontend/src/` — one `.jsx` per page (`/`, `/video`, `/editorial`, `/lab`, `/admin`, `/meli`, `/help`)
- `app-v2/catalog.json` + `app-v2/material-references/` — materials/colours, single source of truth; editable from `/admin`
- `prompts/schemas/sofa.json` — model list + constraints; drives `/api/config` and the UI picker
- `tests/` — prompt-invariant + API smoke tests; `.claude/agents/` — per-concern subagent briefs

## Gotchas
- No `GEMINI_API_KEY` env var by design: users paste keys in the browser; keys travel as a form field per request. Same for OpenRouter/OpenAI keys.
- `/admin` needs `ADMIN_TOKEN` in Docker (loopback-only without it). `CATALOG_GIT_TOKEN/REPO/BRANCH/AUTHOR` (see `.env.example`) make every catalogue save a git commit → CI rebuild → Watchtower rollout.
- Deploy is push-to-`main` only: CI runs tests, builds the image, Watchtower on user machines pulls it within ~5 min. Tags `v*.*.*` also produce a Release zip. Nothing is deployed any other way.
- When `OUTPUTS_DIR` is set (Docker), the catalogue lives in `outputs/catalog/` and is reseeded from the image when `NANO_SOFA_BUILD_SHA` changes unless `pending-push.json` exists. Locally the checked-in files are edited directly — commit them.
- Do not edit `app-v2/frontend/dist/` (gitignored build output). Vite hashes assets; `/catalog.js` is served `no-store` — keep it that way.
- Adding a fabric *type* is a code change in three places: schema enum, `catalog.json`, `.mat-tex.<tex>` CSS in `styles-v2.css`. Adding a model is a schema edit only.
- Respect the invariants in `ARCHITECTURE.md` (material noun must match texture spec; no `person_generation` unless set; no swatch ref in variants/fotosesja). Each was learned by a regression.
- `NANO_SOFA_LOG_PROMPT=1` dumps the full outgoing prompt. Other tunables: `BATCH_CONCURRENCY`, `GEMINI_TIMEOUT_MS`, `MAX_OUTPUT_FILES`.
- `app-v2/` has a dash, so tests import `server.py` by path (`tests/conftest.py`); `studio.*` imports resolve from `app-v2/`.
- `.codex/agents/*.toml` mirror `.claude/agents/*.md` — keep them in sync if you edit one.
