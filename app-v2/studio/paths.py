"""Filesystem layout + logger for the v2 backend.

Everything path-shaped lives here: the app-v2 dir (_THIS), the repo root (put
on sys.path so app.core imports work), the built-frontend dist dir, the
outputs/uploads volume, and the curated scene-reference dir. Import this
module first — it has no intra-package dependencies.
"""

from __future__ import annotations

import logging
import os
import shutil
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
_FRONTEND_DIR = _THIS / "frontend"
_DIST_DIR = _FRONTEND_DIR / "dist"
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

# The catalogue is editable at runtime. In Docker, OUTPUTS_DIR is the mounted
# persistent volume, so both its JSON and reference images live there and
# survive Watchtower replacing the container. Local source development keeps
# using the checked-in files directly, which makes prompt work visible in git.
_BUNDLED_CATALOG_PATH = _THIS / "catalog.json"
_BUNDLED_MATERIAL_REFS_DIR = _THIS / "material-references"
_PERSIST_RUNTIME_CATALOG = bool(os.environ.get("OUTPUTS_DIR"))


def _seed_runtime_catalog(
    output_dir: Path,
    bundled_catalog: Path,
    bundled_references: Path,
) -> tuple[Path, Path]:
    """Create the persistent catalogue once, preserving all later edits."""
    runtime_dir = output_dir / "catalog"
    catalog_path = runtime_dir / "catalog.json"
    references_dir = runtime_dir / "material-references"
    if not catalog_path.is_file():
        runtime_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled_catalog, catalog_path)
    if not references_dir.is_dir():
        if bundled_references.is_dir():
            shutil.copytree(bundled_references, references_dir)
        else:
            references_dir.mkdir(parents=True, exist_ok=True)
    return catalog_path, references_dir


if _PERSIST_RUNTIME_CATALOG:
    _CATALOG_PATH, _MATERIAL_REFS_DIR = _seed_runtime_catalog(
        _OUTPUT_DIR,
        _BUNDLED_CATALOG_PATH,
        _BUNDLED_MATERIAL_REFS_DIR,
    )
else:
    _CATALOG_PATH = _BUNDLED_CATALOG_PATH
    _MATERIAL_REFS_DIR = _BUNDLED_MATERIAL_REFS_DIR

# Recoverable snapshots made by the local catalogue admin before every save.
# They contain the previous catalog.json and only the reference files touched
# by that save.  Keeping a small rolling set makes operator mistakes reversible
# without putting runtime artefacts in git.
_CATALOG_BACKUPS_DIR = _OUTPUT_DIR / "catalog-backups"
_CATALOG_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

# Override the generator's hardcoded outputs dir so it writes to the volume too.
# generator.py reads its dir at import time, so this must run before any call.
try:
    from app.core import generator as _gen_mod
    _gen_mod._OUTPUTS_DIR = _OUTPUT_DIR
except Exception:
    pass
