"""Filesystem layout + logger for the v2 backend.

Everything path-shaped lives here: the app-v2 dir (_THIS), the repo root (put
on sys.path so app.core imports work), the built-frontend dist dir, the
outputs/uploads volume, and the curated scene-reference dir. Import this
module first — it has no intra-package dependencies.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Make the parent project importable so we reuse app.core.generator.
# _THIS is the app-v2 directory (this file lives in app-v2/studio/).
_THIS = Path(__file__).resolve().parent.parent
_REPO_ROOT = _THIS.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nano-sofa-v2")

# Built frontend (Vite). Local dev: run `npm run build` in app-v2/frontend
# (run.sh does it automatically when dist/ is missing), or use `npm run dev`
# for the hot-reloading dev server, which proxies /api here.
_DIST_DIR = _THIS / "frontend" / "dist"
if not _DIST_DIR.is_dir():
    raise RuntimeError(
        "app-v2/frontend/dist not found — build the frontend first: "
        "cd app-v2/frontend && npm install && npm run build"
    )

# OUTPUTS_DIR is the volume mount target in Docker. We keep generator outputs
# and per-request uploads under it so a single bind mount captures everything.
# Falls back to <repo>/outputs for local dev (matches the v1 layout).
_OUTPUT_DIR = Path(os.environ.get("OUTPUTS_DIR") or (_REPO_ROOT / "outputs")).resolve()
_UPLOAD_DIR = _OUTPUT_DIR / "v2-uploads"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Curated scene-reference images live alongside the app, baked into the Docker
# image at /app/app-v2/scene-references/<env_id>.{jpg,png,jpeg}. The lookup is
# best-effort — if no reference is found for an env_id, the prompt falls back
# to the text-only profile.
_SCENE_REFS_DIR = _THIS / "scene-references"

# Override the generator's hardcoded outputs dir so it writes to the volume too.
# generator.py reads its dir at import time, so this must run before any call.
try:
    from app.core import generator as _gen_mod
    _gen_mod._OUTPUTS_DIR = _OUTPUT_DIR
except Exception:
    pass
