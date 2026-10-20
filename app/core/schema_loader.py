"""
schema_loader.py — Loads prompts/schemas/sofa.json and exposes structured
data (preserve lists, system instruction, output vocab) to the generator and
the studio. Model facts come from app.core.model_registry. Watched for changes at startup; call reload() to
re-read from disk without restarting the process.
"""

from __future__ import annotations

import json
import os
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
    """
    Parsed, typed view of sofa.json.

    Attributes are extracted once on construction. Call SofaSchema() again
    (or module-level reload()) to pick up disk changes.
    """

    def __init__(self) -> None:
        raw = _load_raw()
        self._raw = raw

        # ------------------------------------------------------------------ #
        # Models — the schema no longer carries them. app-v2/models.json is
        # the registry; the Gemini ids are mirrored here for the callers that
        # still ask the schema (healthz, validate_request).
        # ------------------------------------------------------------------ #
        self.model_ids: list[str] = [m.id for m in _registry().by_engine("gemini")]

        # ------------------------------------------------------------------ #
        # Reference slots
        # ------------------------------------------------------------------ #
        slot_props = raw["properties"]["reference_slots"]["properties"]
        self.reference_slot_names: list[str] = list(slot_props.keys())
        self.reference_slot_descriptions: dict[str, str] = {
            k: v.get("description", "") for k, v in slot_props.items()
        }

        # ------------------------------------------------------------------ #
        # System instruction default
        # ------------------------------------------------------------------ #
        self.system_instruction_default: str = (
            raw["properties"]["system_instruction"].get("default", "")
        )

        # ------------------------------------------------------------------ #
        # Product fields
        # ------------------------------------------------------------------ #
        prod = raw["properties"]["product"]["properties"]
        self.product_types: list[str] = prod["type"]["enum"]
        self.all_configurations: list[str] = prod["configuration"]["enum"]
        self.frame_style_options: list[str] = (
            prod["frame_style"]["enum"] if "frame_style" in prod else []
        )
        self.preserve_options: list[str] = prod["preserve"]["items"]["enum"]
        self.leg_count_min: int = prod["leg_count"]["minimum"]
        self.leg_count_max: int = prod["leg_count"]["maximum"]

        # Configuration values are pooled in the schema enum but only a subset
        # is relevant for each product type. The split below mirrors the
        # 0.3.0 changelog and is the authoritative source for the UI dropdown.
        self.sofa_configurations: list[str] = [
            "1-seater", "2-seater", "3-seater", "4-seater",
            "corner-left", "corner-right", "modular",
        ]
        self.bed_configurations: list[str] = [
            "twin", "full", "queen", "king", "california-king",
            "european-single", "european-double", "european-king", "super-king",
        ]
        self.configurations_by_type: dict[str, list[str]] = {
            "sofa": self.sofa_configurations,
            "bed": self.bed_configurations,
        }

        # Default preserve list per product type — used to populate the form
        # CheckboxGroup with type-relevant items only. The full enum remains
        # available for users who want to add or remove items.
        self.default_preserve_by_type: dict[str, list[str]] = {
            "sofa": [
                "frame_geometry",
                "cushion_count_and_arrangement",
                "stitching_pattern",
                "piping_and_seam_geometry",
                "armrest_silhouette",
                "seat_depth",
                "overall_proportions",
                "camera_angle",
                "perspective",
                "leg_count_and_positions",
            ],
            "bed": [
                "frame_silhouette",
                "headboard_silhouette",
                "headboard_height",
                "footboard_geometry",
                "footboard_presence",
                "mattress_height",
                "overall_proportions",
                "camera_angle",
                "perspective",
            ],
        }

        # ------------------------------------------------------------------ #
        # Variant fields
        # ------------------------------------------------------------------ #
        uphol = raw["properties"]["variant"]["properties"]["upholstery"]["properties"]
        self.material_options: list[str] = uphol["material"]["enum"]

        # ------------------------------------------------------------------ #
        # Camera fields
        # ------------------------------------------------------------------ #
        cam = raw["properties"]["camera"]["properties"]
        self.angle_options: list[str] = cam["angle"]["enum"]
        self.angle_degrees_options: list[int] = cam["angle_degrees_from_left"]["enum"]
        self.shadow_direction_examples: list[str] = cam["shadow_direction"].get("examples", [])

        # Canonical angle → degrees mapping derived from schema description
        self.angle_to_degrees: dict[str, int] = {
            "front-0": 0,
            "front-34-left": 35,
            "front-34-right": 325,
            "side-90": 90,
            "low-34": 35,
        }

        # ------------------------------------------------------------------ #
        # Output fields
        # ------------------------------------------------------------------ #
        out = raw["properties"]["output"]["properties"]
        self.aspect_ratio_options: list[str] = out["aspect_ratio"]["enum"]
        self.resolution_options: list[str] = out["resolution"]["enum"]
        self.resolution_default: str = out["resolution"].get("default", "1K")
        self.style_default: str = out["style"].get("default", "")

        # ------------------------------------------------------------------ #
        # Negative list defaults
        # ------------------------------------------------------------------ #
        self.negative_defaults: list[str] = raw["properties"]["negative"].get("default", [])

    # ---------------------------------------------------------------------- #
    # Constraint helpers used by the UI
    # ---------------------------------------------------------------------- #

    # The model helpers delegate to the registry so old call sites keep
    # working; new code should import app.core.model_registry directly.
    def max_refs_for_model(self, model_id: str) -> int:
        return _registry().max_refs(model_id, 3)

    def max_resolution_for_model(self, model_id: str) -> str:
        m = _registry().get(model_id)
        return m.max_resolution if m else "1K"

    def supports_resolution_param(self, model_id: str) -> bool:
        m = _registry().get(model_id)
        return bool(m.supports_resolution_param) if m else False

    def resolution_choices_for_model(self, model_id: str) -> list[str]:
        m = _registry().get(model_id)
        return m.resolution_choices() if m else ["1K"]

    def deprecation_date_for_model(self, model_id: str) -> str | None:
        m = _registry().get(model_id)
        return (m.deprecation or {}).get("shutdown") if m else None

    def thinking_on_by_default(self, model_id: str) -> bool:
        m = _registry().get(model_id)
        return bool(m.thinking.get("on_by_default", False)) if m else False

    def thinking_cannot_be_disabled(self, model_id: str) -> bool:
        m = _registry().get(model_id)
        return (not m.thinking.get("can_disable", True)) if m else False

    def aspect_ratios_for_model(self, model_id: str) -> list[str]:
        """
        Newer Gemini image models accept extra extreme ratios; the schema limits
        output.aspect_ratio to the ratios needed for sofa photography, all of
        which are valid on every active model. Return the full schema list.
        """
        return self.aspect_ratio_options


# Module-level singleton — import and use `schema` directly.
schema: SofaSchema = SofaSchema()


def reload() -> SofaSchema:
    """Re-read sofa.json from disk and replace the module singleton."""
    global schema
    schema = SofaSchema()
    return schema
