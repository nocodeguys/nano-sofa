"""FastAPI app assembly: middleware, routers, then the static mount LAST.

The StaticFiles mount on "/" must be registered after every router — a mount
registered earlier would swallow the dynamic routes.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from studio.paths import _DIST_DIR
from studio import routes_generate, routes_pages, routes_video

app = FastAPI(title="Nano Sofa Studio v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(routes_pages.router)
app.include_router(routes_generate.router)
app.include_router(routes_video.router)

# Static files for the prototype JS / CSS — mounted last so dynamic routes win.
app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="static")
