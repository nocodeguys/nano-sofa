"""catalog.json — the single source of truth for materials + colours.

Loaded once here; the browser gets the same data as window.NS_CATALOG via
GET /catalog.js (see routes_pages).
"""

from __future__ import annotations

import json

from studio.paths import _REPO_ROOT, _THIS, logger

# Materials + colours live in catalog.json — the single source of truth shared
# with the browser (served as window.NS_CATALOG via GET /catalog.js). The dicts
# below keep their historical names so the rest of this file is unchanged.
# Per-entry "note" fields in the JSON carry the hard-won prompt rules (EN noun
# must agree with the texture spec — see ARCHITECTURE.md invariant #1).
_CATALOG_PATH = _THIS / "catalog.json"
with open(_CATALOG_PATH, encoding="utf-8") as _f:
    CATALOG = json.load(_f)

# Colour id → English term the prompt uses (TreeTale fabric-matrix GROUPS;
# each carries its representative hex so the model can anchor the exact shade).
_COLOR_PL_TO_EN = {c["id"]: c["prompt_en"] for c in CATALOG["colors"]}

# Material id → short English noun used inline as "{colour} {material}".
_MATERIAL_PL_TO_EN = {m["id"]: m["noun_en"] for m in CATALOG["materials"]}

# Material id → rich texture/drape/features spec. Injected into the prompt's
# "Texture detail:" clause when the user hasn't typed their own material notes
# — see _build_generation_request.
_MATERIAL_TEXTURE_EN = {m["id"]: m["texture_en"] for m in CATALOG["materials"]}


def _validate_catalog() -> None:
    """Fail loudly at startup when catalog.json drifts from the schema enum.

    prompts/schemas/sofa.json is the model-constraints contract; its material
    enum and the catalog must list the same ids, otherwise the UI offers
    materials the schema forbids (or vice versa).
    """
    try:
        with open(_REPO_ROOT / "prompts" / "schemas" / "sofa.json", encoding="utf-8") as f:
            raw = json.load(f)
        enum = set(
            raw["properties"]["variant"]["properties"]["upholstery"]
            ["properties"]["material"]["enum"]
        )
    except (OSError, KeyError, TypeError, ValueError):
        logger.warning("catalog check: could not read material enum from schema")
        return
    catalog_ids = {m["id"] for m in CATALOG["materials"]}
    # The schema enum may carry extra aliases (e.g. legacy names); what must
    # never happen is a catalog material the schema would reject.
    orphans = catalog_ids - enum
    if orphans:
        logger.warning(
            "catalog check: materials missing from schema enum: %s", sorted(orphans)
        )


_validate_catalog()
