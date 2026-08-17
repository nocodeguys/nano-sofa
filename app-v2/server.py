"""
server.py — FastAPI backend for Nano Sofa Studio v2 (thin entry point).

The implementation lives in the studio/ package next to this file:
  studio/paths.py            filesystem layout, logger, dist/outputs dirs
  studio/catalog.py          catalog.json load + validation
  studio/mappings.py         UI-id → English prompt fragment tables
  studio/request_builder.py  FormData → GenerationRequest
  studio/media.py            uploads, delivery formats, EXIF, retention
  studio/routes_pages.py     pages / config / docs / outputs / history
  studio/routes_generate.py  image render endpoints
  studio/routes_video.py     video (Veo) endpoints
  studio/app.py              FastAPI app assembly (static mount LAST)

Serves the built Vite frontend from ./frontend/dist and exposes:
  GET  /                   → index.html (configurator)
  GET  /healthz            → liveness + capability report (no API call)
  GET  /api/config         → model enum + per-model constraints
  POST /api/generate       → run a single generation
  GET  /api/outputs/<file> → serve a generated image

Wraps app/core/generator.py from the parent project.

Environment variables:
  PORT          listen port (default 7861)
  HOST          listen host (default 0.0.0.0)
  OUTPUTS_DIR   where generated images and uploads live (default <repo>/outputs)
                Mount this as a volume in Docker to persist renders.

Run with:
    cd <repo-root> && python app-v2/server.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# app-v2 is a dashed directory, so the studio package can't be imported from
# the repo root — this file's own directory must be on sys.path. Covers all
# three entry modes: `python app-v2/server.py`, run.sh, and the by-path
# importlib load the tests use (which does NOT set sys.path[0] to app-v2).
_THIS = Path(__file__).resolve().parent
if str(_THIS) not in sys.path:
    sys.path.insert(0, str(_THIS))

from studio.app import app  # noqa: E402,F401
from studio.paths import _OUTPUT_DIR, logger  # noqa: E402

# Re-exports for test / back-compat: tests import this module by path and
# reach these names as attributes (see tests/conftest.py + test_prompt_invariants).
from studio.catalog import (  # noqa: E402,F401
    CATALOG,
    _COLOR_PL_TO_EN,
    _MATERIAL_PL_TO_EN,
    _MATERIAL_TEXTURE_EN,
)
from studio.request_builder import _build_generation_request  # noqa: E402,F401


def main() -> None:
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 7861))
    log_level = os.environ.get("LOG_LEVEL", "info")
    logger.info("Nano Sofa v2 starting on http://%s:%d  (outputs=%s)", host, port, _OUTPUT_DIR)
    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
