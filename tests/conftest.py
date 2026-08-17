"""Shared fixtures: import the FastAPI server module and app.core helpers.

server.py lives in a dashed directory (app-v2/), so it is imported by path.
Importing it requires app-v2/frontend/dist to exist (the server refuses to
start without the built frontend) — CI builds the frontend before pytest.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_server():
    spec = importlib.util.spec_from_file_location(
        "nano_sofa_server", REPO_ROOT / "app-v2" / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def server():
    return _load_server()


@pytest.fixture(scope="session")
def base_image(tmp_path_factory) -> Path:
    """A tiny valid PNG standing in for the uploaded product photo."""
    path = tmp_path_factory.mktemp("img") / "base.png"
    Image.new("RGB", (32, 32), (200, 190, 180)).save(path)
    return path
