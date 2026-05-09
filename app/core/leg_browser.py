"""
leg_browser.py — Reads legs/manifest.json and provides structured access
to leg entries for the UI. Handles angle matching and descriptor retrieval.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _REPO_ROOT / "legs" / "manifest.json"

# Canonical angle slug mapping: sofa.json camera angle enum → manifest slug
ANGLE_SLUG_MAP: dict[str, str] = {
    "front-0": "front0",
    "front-34-left": "front34l",
    "front-34-right": "front34r",
    "side-90": "side90",
    "low-34": "low34",
}


def _load_manifest() -> dict[str, Any]:
    with open(_MANIFEST_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


class LegEntry:
    """Typed view of a single manifest entry."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.id: str = raw["id"]
        self.style: str = raw["style"]
        self.material: str = raw["material"]
        self.material_slug: str = raw.get("material_slug", "")
        self.explicit_descriptor: str = raw.get("explicit_descriptor", "")
        self.geometry: dict[str, Any] = raw.get("geometry", {})
        self.angles_available: list[str] = raw.get("angles_available", [])
        self.renders: dict[str, str] = raw.get("renders", {})
        self.tags: list[str] = raw.get("tags", [])
        self.shadow_direction_hint: str = raw.get("shadow_direction_hint", "4 o-clock")
        self.license: str = raw.get("license", "CC0")

    def render_path_for_angle(self, camera_angle: str) -> Path | None:
        """
        Return the resolved render PNG path for the given camera angle enum
        value (e.g. 'front-34-left'). Returns None if:
        - The angle slug is not in renders, or
        - The renders dict is empty (renders not yet generated).
        """
        slug = ANGLE_SLUG_MAP.get(camera_angle)
        if not slug:
            return None
        rel_path = self.renders.get(slug)
        if not rel_path:
            return None
        resolved = _REPO_ROOT / rel_path
        return resolved if resolved.exists() else None

    def best_angle_for(self, camera_angle: str) -> str:
        """
        Return the best available angle slug for the given camera angle.
        Falls back to adjacent angles if the exact one has no render.
        """
        desired_slug = ANGLE_SLUG_MAP.get(camera_angle, "front34l")
        fallback_order = ["front34l", "front34r", "front0", "side90", "low34"]
        if desired_slug in self.angles_available:
            return desired_slug
        for slug in fallback_order:
            if slug in self.angles_available:
                return slug
        return self.angles_available[0] if self.angles_available else "front34l"

    @property
    def display_label(self) -> str:
        """Short label for dropdown display."""
        return f"{self.id}  —  {self.material}"

    @property
    def style_family(self) -> str:
        return self.style

    def __repr__(self) -> str:
        return f"LegEntry(id={self.id!r}, style={self.style!r})"


class LegBrowser:
    """
    Container for all manifest entries with filtering and lookup helpers.
    """

    def __init__(self) -> None:
        raw = _load_manifest()
        self._legs_raw: dict[str, Any] = raw.get("legs", {})
        self.entries: dict[str, LegEntry] = {
            leg_id: LegEntry(data)
            for leg_id, data in self._legs_raw.items()
        }
        self.schema_version: str = raw.get("$schema_version", "unknown")

    def reload(self) -> None:
        raw = _load_manifest()
        self._legs_raw = raw.get("legs", {})
        self.entries = {
            leg_id: LegEntry(data)
            for leg_id, data in self._legs_raw.items()
        }

    def all_ids(self) -> list[str]:
        return list(self.entries.keys())

    def get(self, leg_id: str) -> LegEntry | None:
        return self.entries.get(leg_id)

    def by_style(self, style: str) -> list[LegEntry]:
        return [e for e in self.entries.values() if e.style == style]

    def style_families(self) -> list[str]:
        seen: list[str] = []
        for e in self.entries.values():
            if e.style not in seen:
                seen.append(e.style)
        return seen

    def dropdown_choices(self) -> list[str]:
        """Ordered list of display labels for a Gradio Dropdown."""
        return [e.display_label for e in self.entries.values()]

    def id_from_label(self, label: str) -> str | None:
        """Reverse-map a display label back to the leg ID."""
        for leg_id, entry in self.entries.items():
            if entry.display_label == label:
                return leg_id
        # Fallback: label might already be a bare ID
        if label in self.entries:
            return label
        return None

    def dropdown_choices_with_ids(self) -> list[tuple[str, str]]:
        """
        List of (display_label, leg_id) tuples — use with Gradio Dropdown
        when the value should be the ID rather than the label string.
        """
        return [(e.display_label, leg_id) for leg_id, e in self.entries.items()]

    def render_path_for(self, leg_id: str, camera_angle: str) -> Path | None:
        entry = self.get(leg_id)
        if not entry:
            return None
        return entry.render_path_for_angle(camera_angle)

    def explicit_descriptor_for(self, leg_id: str) -> str:
        entry = self.get(leg_id)
        return entry.explicit_descriptor if entry else ""

    def shadow_hint_for(self, leg_id: str) -> str:
        entry = self.get(leg_id)
        return entry.shadow_direction_hint if entry else "4 o-clock"


# Module-level singleton
leg_browser: LegBrowser = LegBrowser()


def reload() -> LegBrowser:
    """Re-read manifest.json from disk and refresh the singleton."""
    leg_browser.reload()
    return leg_browser
