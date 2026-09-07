"""catalog.json — the single source of truth for materials + colours.

The dictionaries in this module deliberately keep a stable object identity.
The admin panel can therefore reload their contents after a validated save and
every module that imported them sees the new values immediately — no server
restart and no split brain between the prompt builder and ``/catalog.js``.
"""

from __future__ import annotations

import json

from studio.paths import _CATALOG_PATH, _REPO_ROOT, logger

# Materials + colours live in catalog.json — the single source of truth shared
# with the browser (served as window.NS_CATALOG via GET /catalog.js). The dicts
# below keep their historical names so the rest of this file is unchanged.
# Per-entry "note" fields in the JSON carry the hard-won prompt rules (EN noun
# must agree with the texture spec — see ARCHITECTURE.md invariant #1).
def _read_catalog() -> dict:
    with open(_CATALOG_PATH, encoding="utf-8") as catalog_file:
        return json.load(catalog_file)


CATALOG = _read_catalog()


def flatten_colors(catalog: dict) -> list[dict]:
    """Every selectable colour as one flat list: the universal colour GROUPS
    from ``colors`` plus every code of every fabric ``collection``.

    A collection code becomes a colour with id ``<collection>-<code>`` (e.g.
    ``velutto-27``), its own exact hex, the collection's material, and a
    ``fabric_code`` label that is stamped into render metadata. This is the
    single flattening used by the prompt tables AND by the browser (served
    inside /catalog.js as ``color_index``), so the two never disagree.
    """
    flat: list[dict] = []
    for color in catalog.get("colors", []):
        flat.append({
            "id": color["id"],
            "name_pl": color["name_pl"],
            "hex": color["hex"],
            "prompt_en": color["prompt_en"],
            "fabric": bool(color.get("fabric", True)),
            "covers": color.get("covers", ""),
            "collection": "",
            "code": "",
            "material": "",
            "fabric_code": "",
            "hex_verified": True,
        })
    for collection in catalog.get("collections", []):
        cid = collection["id"]
        cname = collection.get("name_pl") or cid
        for entry in collection.get("codes", []):
            code = str(entry["code"])
            hex_value = entry["hex"]
            name = entry.get("name_pl") or f"{cname} {code}"
            prompt_en = entry.get("prompt_en") or (
                f"{name} — exact upholstery colour hex {hex_value}"
            )
            flat.append({
                "id": entry.get("id") or f"{cid}-{code}",
                "name_pl": name,
                "hex": hex_value,
                "prompt_en": prompt_en,
                "fabric": True,
                "covers": "",
                "collection": cid,
                "code": code,
                "material": collection.get("material", ""),
                "fabric_code": f"{cname} {code}",
                "hex_verified": bool(entry.get("hex_verified", True)),
            })
    return flat


def catalog_for_browser(catalog: dict | None = None) -> dict:
    """The catalog as served to the browser: raw data plus the flattened
    ``color_index`` so data.jsx does not re-implement the flattening."""
    source = CATALOG if catalog is None else catalog
    return {**source, "color_index": flatten_colors(source)}


# Colour id → English term the prompt uses (TreeTale fabric-matrix GROUPS and
# collection codes; each carries its hex so the model can anchor the shade).
_COLOR_PL_TO_EN = {c["id"]: c["prompt_en"] for c in flatten_colors(CATALOG)}

# Colour id → structured identity (hex, collection, code, implied material,
# fabric_code label). The prompt builder stamps these into the render.
_COLOR_META = {c["id"]: c for c in flatten_colors(CATALOG)}

# Material id → short English noun used inline as "{colour} {material}".
_MATERIAL_PL_TO_EN = {m["id"]: m["noun_en"] for m in CATALOG["materials"]}

# Material id → rich texture/drape/features spec. Injected into the prompt's
# "Texture detail:" clause when the user hasn't typed their own material notes
# — see _build_generation_request.
_MATERIAL_TEXTURE_EN = {m["id"]: m["texture_en"] for m in CATALOG["materials"]}

# Material-specific failure modes that should be excluded explicitly.  Text
# alone is less reliable than the canonical swatch, but these negatives stop
# visually adjacent fabrics from winning when the product is shown at hero
# distance and the individual yarn loops become small.
_MATERIAL_NEGATIVES_EN = {
    m["id"]: list(m.get("avoid_en", [])) for m in CATALOG["materials"]
}


def reload_catalog(catalog: dict | None = None) -> dict:
    """Atomically refresh all in-memory catalogue views in place.

    ``request_builder`` and ``routes_pages`` import these dicts directly.  A
    reassignment here would leave those imports stale, so every mapping is
    mutated in place.  The caller validates the payload before invoking this
    function; reading from disk remains useful for startup and recovery.
    """
    fresh = catalog if catalog is not None else _read_catalog()

    flat = flatten_colors(fresh)
    colors = {c["id"]: c["prompt_en"] for c in flat}
    color_meta = {c["id"]: c for c in flat}
    material_nouns = {m["id"]: m["noun_en"] for m in fresh["materials"]}
    material_textures = {m["id"]: m["texture_en"] for m in fresh["materials"]}
    material_negatives = {
        m["id"]: list(m.get("avoid_en", [])) for m in fresh["materials"]
    }

    CATALOG.clear()
    CATALOG.update(fresh)
    _COLOR_PL_TO_EN.clear()
    _COLOR_PL_TO_EN.update(colors)
    _COLOR_META.clear()
    _COLOR_META.update(color_meta)
    _MATERIAL_PL_TO_EN.clear()
    _MATERIAL_PL_TO_EN.update(material_nouns)
    _MATERIAL_TEXTURE_EN.clear()
    _MATERIAL_TEXTURE_EN.update(material_textures)
    _MATERIAL_NEGATIVES_EN.clear()
    _MATERIAL_NEGATIVES_EN.update(material_negatives)
    return CATALOG


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
