"""
schema_loader.py — Loads prompts/schemas/sofa.json: the request CONTRACT
(product identity to preserve, variant axes, camera, output vocabulary and
the system-instruction persona). Model facts come from
app.core.model_registry; materials, colours and backdrops from
app-v2/catalog.json. Call reload() to re-read the file without restarting.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Resolve paths relative to this file so the app works from any cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = _REPO_ROOT / "prompts" / "schemas" / "sofa.json"


def _registry():
    from app.core.model_registry import registry
    return registry


def _load_raw() -> dict[str, Any]:
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


class SofaSchema:
    """Parsed view of sofa.json — only what the server actually reads."""

    def __init__(self) -> None:
        raw = _load_raw()
        self._raw = raw
        props = raw["properties"]

        # Gemini ids, mirrored from the registry for the callers that still
        # ask the schema (healthz, validate_request).
        self.model_ids: list[str] = [m.id for m in _registry().by_engine("gemini")]

        # The persona Gemini gets as system instruction and the other engines
        # as the first paragraph of the prompt (see app/core/prompt).
        self.system_instruction_default: str = props["system_instruction"].get("default", "")

        prod = props["product"]["properties"]
        self.product_types: list[str] = prod["type"]["enum"]
        self.all_configurations: list[str] = prod["configuration"]["enum"]
        self.frame_style_options: list[str] = prod.get("frame_style", {}).get("enum", [])
        self.preserve_options: list[str] = prod["preserve"]["items"]["enum"]
        self.leg_count_min: int = prod["leg_count"]["minimum"]
        self.leg_count_max: int = prod["leg_count"]["maximum"]

        # The material enum is the contract catalog.json is validated against
        # at startup and on every admin save (studio/catalog.py, routes_admin).
        uphol = props["variant"]["properties"]["upholstery"]["properties"]
        self.material_options: list[str] = uphol["material"]["enum"]

        cam = props["camera"]["properties"]
        self.angle_options: list[str] = cam["angle"]["enum"]
        self.angle_degrees_options: list[int] = cam["angle_degrees_from_left"]["enum"]

        out = props["output"]["properties"]
        self.aspect_ratio_options: list[str] = out["aspect_ratio"]["enum"]
        self.resolution_options: list[str] = out["resolution"]["enum"]
        self.resolution_default: str = out["resolution"].get("default", "1K")

    # ---- model helpers (registry-backed; kept for old call sites) -------- #
    def max_refs_for_model(self, model_id: str) -> int:
        return _registry().max_refs(model_id, 3)

    def supports_resolution_param(self, model_id: str) -> bool:
        m = _registry().get(model_id)
        return bool(m.supports_resolution_param) if m else False

    def resolution_choices_for_model(self, model_id: str) -> list[str]:
        m = _registry().get(model_id)
        return m.resolution_choices() if m else ["1K"]

    def thinking_on_by_default(self, model_id: str) -> bool:
        m = _registry().get(model_id)
        return bool(m.thinking.get("on_by_default", False)) if m else False


# Module-level singleton — import and use `schema` directly.
schema: SofaSchema = SofaSchema()


def reload() -> SofaSchema:
    """Re-read sofa.json from disk and replace the module singleton."""
    global schema
    schema = SofaSchema()
    return schema
