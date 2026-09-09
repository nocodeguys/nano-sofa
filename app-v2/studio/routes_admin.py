"""Catalogue administration with validation, rollback and repository push.

A save is a transaction: validate the catalogue and images, snapshot the old
files, atomically promote the new files, refresh the stable in-memory
catalogue dictionaries (the running instance is correct immediately), and
then — when CATALOG_GIT_TOKEN is configured — commit catalog.json plus the
material references to the repository so CI rebuilds the image and every
other instance receives the same catalogue. A failed local step restores the
previous working version; a failed push keeps the edit locally and marks it
as waiting for a retry.

Access: with ADMIN_TOKEN set (every Docker deployment), requests must carry
it in ``X-Admin-Token`` (or ``Authorization: Bearer``). Without it the panel
is loopback-only, which is the source-mode developer setup.
"""

from __future__ import annotations

import asyncio
import hmac
import io
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from studio.catalog import CATALOG, _CATALOG_PATH, flatten_colors, reload_catalog
from studio.catalog_git import (
    CatalogGitError,
    load_config as load_git_config,
    push_catalog,
    read_json,
    workflow_status,
    write_json,
)
from studio.paths import (
    _CATALOG_BACKUPS_DIR,
    _DIST_DIR,
    _LAST_PUSH_PATH,
    _MATERIAL_REFS_DIR,
    _PENDING_PUSH_PATH,
    _PERSIST_RUNTIME_CATALOG,
    logger,
    page_response,
)

router = APIRouter()

_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")
_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_REFERENCE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
# Photos are stored as JPEG at ≤ 2048 px: a 4096² PNG re-encode of a phone
# photo is 10–40 MB and every save would add that much to the repository.
_REFERENCE_MAX_SIDE = int(os.environ.get("CATALOG_REFERENCE_MAX_SIDE", "2048"))
_REFERENCE_JPEG_QUALITY = 90
_SAVE_LOCK = asyncio.Lock()
_BUILD_STATE: dict = {"state": "idle", "message": "Gotowy", "updated_at": None}
# CSS texture previews known to styles-v2.css (.mat-tex.<tex>). Kept here so
# the admin can offer them without the browser hard-coding the list.
_KNOWN_TEX = ["linen", "boucle", "weave", "chenille", "cremona", "leather", "velvet", "corduroy"]


def _admin_token() -> str:
    return os.environ.get("ADMIN_TOKEN", "").strip()


def _supplied_token(request: Request) -> str:
    header = request.headers.get("x-admin-token", "").strip()
    if header:
        return header
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _require_admin(request: Request) -> None:
    """Gate every write-capable admin route.

    Token mode (ADMIN_TOKEN set — every Docker deployment): the request must
    carry the token. Loopback mode (no token — source-mode development): only
    this computer may call, and the Origin header must be loopback too so an
    unrelated website open in the browser cannot post here while permissive
    API CORS is enabled for the Vite dev server.
    """
    token = _admin_token()
    if token:
        supplied = _supplied_token(request)
        if not supplied or not hmac.compare_digest(supplied, token):
            raise HTTPException(
                401,
                "Panel Katalog wymaga tokenu administratora (ADMIN_TOKEN).",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return
    client_host = request.client.host if request.client else ""
    local_hosts = {"127.0.0.1", "::1", "localhost", "testclient"}
    if client_host not in local_hosts:
        raise HTTPException(
            403,
            "Panel Katalog działa bez tokenu tylko lokalnie. W Dockerze ustaw ADMIN_TOKEN w .env.",
        )
    origin = request.headers.get("origin")
    if origin:
        origin_host = (urlparse(origin).hostname or "").lower()
        if origin_host not in {"127.0.0.1", "::1", "localhost"}:
            raise HTTPException(403, "Nieprawidłowe źródło żądania administracyjnego.")


# Back-compat alias for anything importing the old name.
_require_local = _require_admin


def _nonempty_string(value: object, label: str, *, max_length: int = 8000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: pole nie może być puste")
    result = value.strip()
    if len(result) > max_length:
        raise ValueError(f"{label}: maksymalnie {max_length} znaków")
    return result


def validate_catalog(payload: object) -> dict:
    """Validate and normalize a catalogue submitted by the admin UI."""
    if not isinstance(payload, dict):
        raise ValueError("Katalog musi być obiektem JSON.")
    materials = payload.get("materials")
    colors = payload.get("colors")
    if not isinstance(materials, list) or not materials:
        raise ValueError("Katalog musi zawierać co najmniej jedną tkaninę.")
    if not isinstance(colors, list) or not colors:
        raise ValueError("Katalog musi zawierać co najmniej jeden kolor.")
    if len(materials) > 50 or len(colors) > 100:
        raise ValueError("Katalog jest zbyt duży (maks. 50 tkanin i 100 kolorów).")

    normalized_materials: list[dict] = []
    material_ids: set[str] = set()
    for index, raw in enumerate(materials, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"Tkanina {index}: nieprawidłowy rekord")
        item = dict(raw)
        material_id = _nonempty_string(item.get("id"), f"Tkanina {index} / ID", max_length=48)
        if not _ID_RE.fullmatch(material_id):
            raise ValueError(f"Tkanina {index}: ID może zawierać małe litery, cyfry, _ i -")
        if material_id in material_ids:
            raise ValueError(f"Powtórzone ID tkaniny: {material_id}")
        material_ids.add(material_id)
        item["id"] = material_id
        for key, label, limit in (
            ("name_pl", "nazwa", 120),
            ("prop_pl", "krótki opis", 240),
            ("finish_pl", "wykończenie", 80),
            ("tex", "typ podglądu", 48),
            ("noun_en", "nazwa dla modelu", 240),
            ("texture_en", "opis faktury", 8000),
        ):
            item[key] = _nonempty_string(item.get(key), f"{material_id} / {label}", max_length=limit)
        avoid = item.get("avoid_en", [])
        if not isinstance(avoid, list) or any(not isinstance(v, str) for v in avoid):
            raise ValueError(f"{material_id} / wykluczenia: oczekiwana lista tekstów")
        item["avoid_en"] = [v.strip() for v in avoid if v.strip()]
        normalized_materials.append(item)

    # Material IDs are also a JSON-schema contract used by the generator.  The
    # admin edits descriptions and swatches; adding/removing a type requires a
    # code/schema migration and must not happen accidentally in this panel.
    try:
        from app.core.schema_loader import schema

        allowed = set(schema.material_options)
        if material_ids != allowed:
            missing = sorted(allowed - material_ids)
            extra = sorted(material_ids - allowed)
            details = []
            if missing:
                details.append("brakuje: " + ", ".join(missing))
            if extra:
                details.append("spoza schematu: " + ", ".join(extra))
            raise ValueError("Lista typów tkanin nie zgadza się ze schematem (" + "; ".join(details) + ").")
    except (AttributeError, KeyError, TypeError):
        logger.warning("admin catalog: could not verify material schema enum")

    normalized_colors: list[dict] = []
    color_ids: set[str] = set()
    for index, raw in enumerate(colors, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"Kolor {index}: nieprawidłowy rekord")
        item = dict(raw)
        color_id = _nonempty_string(item.get("id"), f"Kolor {index} / ID", max_length=48)
        if not _ID_RE.fullmatch(color_id):
            raise ValueError(f"Kolor {index}: ID może zawierać małe litery, cyfry, _ i -")
        if color_id in color_ids:
            raise ValueError(f"Powtórzone ID koloru: {color_id}")
        color_ids.add(color_id)
        item["id"] = color_id
        item["name_pl"] = _nonempty_string(item.get("name_pl"), f"{color_id} / nazwa", max_length=120)
        item["prompt_en"] = _nonempty_string(item.get("prompt_en"), f"{color_id} / opis dla modelu", max_length=2000)
        color_hex = _nonempty_string(item.get("hex"), f"{color_id} / HEX", max_length=7).upper()
        if not _HEX_RE.fullmatch(color_hex):
            raise ValueError(f"{color_id}: kolor musi mieć format #RRGGBB")
        item["hex"] = color_hex
        item["fabric"] = bool(item.get("fabric", True))
        if "covers" in item and item["covers"] is not None and not isinstance(item["covers"], str):
            raise ValueError(f"{color_id} / próbki: oczekiwany tekst")
        normalized_colors.append(item)
    if "greige" not in color_ids:
        raise ValueError("Kolor bazowy „greige” nie może zostać usunięty.")

    raw_collections = payload.get("collections", [])
    if raw_collections is None:
        raw_collections = []
    if not isinstance(raw_collections, list) or len(raw_collections) > 50:
        raise ValueError("Kolekcje: oczekiwana lista (maks. 50).")
    normalized_collections: list[dict] = []
    collection_ids: set[str] = set()
    for index, raw in enumerate(raw_collections, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"Kolekcja {index}: nieprawidłowy rekord")
        item = dict(raw)
        collection_id = _nonempty_string(item.get("id"), f"Kolekcja {index} / ID", max_length=48)
        if not _ID_RE.fullmatch(collection_id):
            raise ValueError(f"Kolekcja {index}: ID może zawierać małe litery, cyfry, _ i -")
        if collection_id in collection_ids:
            raise ValueError(f"Powtórzone ID kolekcji: {collection_id}")
        collection_ids.add(collection_id)
        item["id"] = collection_id
        item["name_pl"] = _nonempty_string(item.get("name_pl"), f"{collection_id} / nazwa", max_length=120)
        material_id = _nonempty_string(item.get("material"), f"{collection_id} / tkanina", max_length=48)
        if material_id not in material_ids:
            raise ValueError(f"{collection_id}: tkanina „{material_id}” nie istnieje w katalogu")
        item["material"] = material_id
        description = item.get("description_pl", "")
        if description is not None and not isinstance(description, str):
            raise ValueError(f"{collection_id} / opis: oczekiwany tekst")
        item["description_pl"] = (description or "").strip()[:1000]
        codes = item.get("codes", [])
        if codes is None:
            codes = []
        if not isinstance(codes, list) or len(codes) > 200:
            raise ValueError(f"{collection_id}: kody muszą być listą (maks. 200)")
        normalized_codes: list[dict] = []
        seen_codes: set[str] = set()
        for code_index, raw_code in enumerate(codes, 1):
            if not isinstance(raw_code, dict):
                raise ValueError(f"{collection_id} / kod {code_index}: nieprawidłowy rekord")
            entry = dict(raw_code)
            code = str(entry.get("code", "")).strip()
            if not code or not _CODE_RE.fullmatch(code):
                raise ValueError(f"{collection_id} / kod {code_index}: nieprawidłowy kod tkaniny")
            if code.lower() in seen_codes:
                raise ValueError(f"{collection_id}: powtórzony kod {code}")
            seen_codes.add(code.lower())
            entry["code"] = code
            code_hex = _nonempty_string(entry.get("hex"), f"{collection_id} {code} / HEX", max_length=7).upper()
            if not _HEX_RE.fullmatch(code_hex):
                raise ValueError(f"{collection_id} {code}: kolor musi mieć format #RRGGBB")
            entry["hex"] = code_hex
            name = entry.get("name_pl", "")
            if name is not None and not isinstance(name, str):
                raise ValueError(f"{collection_id} {code} / nazwa: oczekiwany tekst")
            entry["name_pl"] = (name or "").strip()[:120] or f"{item['name_pl']} {code}"
            prompt_en = entry.get("prompt_en", "")
            if prompt_en is not None and not isinstance(prompt_en, str):
                raise ValueError(f"{collection_id} {code} / opis dla modelu: oczekiwany tekst")
            prompt_en = (prompt_en or "").strip()
            if len(prompt_en) > 2000:
                raise ValueError(f"{collection_id} {code}: opis dla modelu maks. 2000 znaków")
            entry["prompt_en"] = prompt_en or f"{entry['name_pl']} — exact upholstery colour hex {code_hex}"
            entry["hex_verified"] = bool(entry.get("hex_verified", True))
            group = entry.get("group", "")
            entry["group"] = group if isinstance(group, str) and group in color_ids else ""
            explicit_id = entry.get("id")
            if explicit_id is not None:
                if not isinstance(explicit_id, str) or not _ID_RE.fullmatch(explicit_id):
                    raise ValueError(f"{collection_id} {code}: nieprawidłowe ID koloru")
            normalized_codes.append(entry)
        item["codes"] = normalized_codes
        normalized_collections.append(item)

    result = dict(payload)
    result["materials"] = normalized_materials
    result["colors"] = normalized_colors
    result["collections"] = normalized_collections
    flat_ids = [c["id"] for c in flatten_colors(result)]
    duplicates = sorted({cid for cid in flat_ids if flat_ids.count(cid) > 1})
    if duplicates:
        raise ValueError("Powtórzone ID koloru po spłaszczeniu kolekcji: " + ", ".join(duplicates))
    return result


def _reference_path(material_id: str) -> Path | None:
    for extension in _REFERENCE_EXTENSIONS:
        candidate = _MATERIAL_REFS_DIR / f"{material_id}{extension}"
        if candidate.is_file():
            return candidate
    return None


def _application_reference_path(material_id: str) -> Path | None:
    for extension in _REFERENCE_EXTENSIONS:
        candidate = _MATERIAL_REFS_DIR / f"{material_id}-application{extension}"
        if candidate.is_file():
            return candidate
    return None


_VIEW_REFERENCE_SUFFIXES = {
    "left": "-left",
    "right": "-right",
    "behavior": "-behavior",
}


def _view_reference_path(material_id: str, role: str) -> Path | None:
    suffix = _VIEW_REFERENCE_SUFFIXES.get(role)
    if suffix is None:
        return None
    for extension in _REFERENCE_EXTENSIONS:
        candidate = _MATERIAL_REFS_DIR / f"{material_id}{suffix}{extension}"
        if candidate.is_file():
            return candidate
    return None


def _prepare_reference(
    data: bytes,
    material_id: str,
    target_dir: Path,
    *,
    filename_suffix: str = "",
) -> Path:
    if not data:
        raise ValueError(f"{material_id}: pusty plik referencji")
    if len(data) > 20 * 1024 * 1024:
        raise ValueError(f"{material_id}: referencja może mieć maksymalnie 20 MB")
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source)
            image.load()
            if image.width < 128 or image.height < 128:
                raise ValueError(f"{material_id}: referencja musi mieć co najmniej 128×128 px")
            if image.width > _REFERENCE_MAX_SIDE or image.height > _REFERENCE_MAX_SIDE:
                image.thumbnail((_REFERENCE_MAX_SIDE, _REFERENCE_MAX_SIDE), Image.Resampling.LANCZOS)
            # Photographs of fabric have no alpha worth keeping; JPEG at q90
            # is visually lossless for the model and 5–10× smaller than PNG,
            # which matters because every save is committed to the repo.
            image = image.convert("RGB")
            destination = target_dir / f"{material_id}{filename_suffix}.jpg"
            image.save(destination, format="JPEG", quality=_REFERENCE_JPEG_QUALITY, optimize=True)
            return destination
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"{material_id}: plik nie jest poprawnym obrazem") from exc


def _set_build_state(state: str, message: str) -> None:
    _BUILD_STATE.update({"state": state, "message": message, "updated_at": int(time.time())})


def _write_backup(
    old_catalog: bytes,
    touched_ids: set[str],
    touched_application_ids: set[str],
    touched_view_keys: set[tuple[str, str]],
) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    destination = _CATALOG_BACKUPS_DIR / f"catalog-{timestamp}-{time.time_ns() % 1_000_000:06d}.zip"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("catalog.json", old_catalog)
        manifest: dict[str, dict[str, str | None]] = {
            "texture": {},
            "application": {},
            "views": {},
        }
        for material_id in sorted(touched_ids):
            path = _reference_path(material_id)
            manifest["texture"][material_id] = path.name if path else None
            if path:
                archive.write(path, f"material-references/{path.name}")
        for material_id in sorted(touched_application_ids):
            path = _application_reference_path(material_id)
            manifest["application"][material_id] = path.name if path else None
            if path:
                archive.write(path, f"material-references/{path.name}")
        for material_id, role in sorted(touched_view_keys):
            path = _view_reference_path(material_id, role)
            key = f"{material_id}:{role}"
            manifest["views"][key] = path.name if path else None
            if path:
                archive.write(path, f"material-references/{path.name}")
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    backups = sorted(_CATALOG_BACKUPS_DIR.glob("catalog-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in backups[10:]:
        stale.unlink(missing_ok=True)
    return destination


def _commit_update(
    catalog: dict,
    replacements: dict[str, bytes],
    deletions: set[str],
    application_replacements: dict[str, bytes] | None = None,
    application_deletions: set[str] | None = None,
    view_replacements: dict[tuple[str, str], bytes] | None = None,
    view_deletions: set[tuple[str, str]] | None = None,
) -> dict:
    application_replacements = application_replacements or {}
    application_deletions = application_deletions or set()
    view_replacements = view_replacements or {}
    view_deletions = view_deletions or set()
    old_catalog = _CATALOG_PATH.read_bytes()
    touched_ids = set(replacements) | set(deletions)
    touched_application_ids = set(application_replacements) | set(application_deletions)
    touched_view_keys = set(view_replacements) | set(view_deletions)
    old_references: dict[str, tuple[str, bytes] | None] = {}
    for material_id in touched_ids:
        existing = _reference_path(material_id)
        old_references[material_id] = (existing.suffix, existing.read_bytes()) if existing else None
    old_application_references: dict[str, tuple[str, bytes] | None] = {}
    for material_id in touched_application_ids:
        existing = _application_reference_path(material_id)
        old_application_references[material_id] = (
            (existing.suffix, existing.read_bytes()) if existing else None
        )
    old_view_references: dict[tuple[str, str], tuple[str, bytes] | None] = {}
    for material_id, role in touched_view_keys:
        existing = _view_reference_path(material_id, role)
        old_view_references[(material_id, role)] = (
            (existing.suffix, existing.read_bytes()) if existing else None
        )

    _MATERIAL_REFS_DIR.mkdir(parents=True, exist_ok=True)
    # Keep staging on the same filesystem as the runtime catalogue. In Docker
    # that target is a mounted volume; same-filesystem os.replace gives us an
    # atomic promotion and avoids EXDEV across the container layer boundary.
    staging_parent = Path(
        tempfile.mkdtemp(prefix=".admin-save-", dir=_CATALOG_PATH.parent)
    )
    staged_refs = staging_parent / "references"
    staged_refs.mkdir()
    temp_catalog = _CATALOG_PATH.with_suffix(".json.admin-tmp")
    backup_path: Path | None = None
    try:
        for material_id, data in replacements.items():
            _prepare_reference(data, material_id, staged_refs)
        for material_id, data in application_replacements.items():
            _prepare_reference(
                data,
                material_id,
                staged_refs,
                filename_suffix="-application",
            )
        for (material_id, role), data in view_replacements.items():
            _prepare_reference(
                data,
                material_id,
                staged_refs,
                filename_suffix=_VIEW_REFERENCE_SUFFIXES[role],
            )

        _set_build_state("building", "Walidacja zakończona. Zapisuję katalog…")
        backup_path = _write_backup(
            old_catalog,
            touched_ids,
            touched_application_ids,
            touched_view_keys,
        )

        temp_catalog.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_catalog, _CATALOG_PATH)

        for material_id in touched_ids:
            for extension in _REFERENCE_EXTENSIONS:
                (_MATERIAL_REFS_DIR / f"{material_id}{extension}").unlink(missing_ok=True)
        for material_id in replacements:
            os.replace(staged_refs / f"{material_id}.jpg", _MATERIAL_REFS_DIR / f"{material_id}.jpg")
        for material_id in touched_application_ids:
            for extension in _REFERENCE_EXTENSIONS:
                (_MATERIAL_REFS_DIR / f"{material_id}-application{extension}").unlink(missing_ok=True)
        for material_id in application_replacements:
            os.replace(
                staged_refs / f"{material_id}-application.jpg",
                _MATERIAL_REFS_DIR / f"{material_id}-application.jpg",
            )
        for material_id, role in touched_view_keys:
            suffix = _VIEW_REFERENCE_SUFFIXES[role]
            for extension in _REFERENCE_EXTENSIONS:
                (_MATERIAL_REFS_DIR / f"{material_id}{suffix}{extension}").unlink(
                    missing_ok=True
                )
        for material_id, role in view_replacements:
            suffix = _VIEW_REFERENCE_SUFFIXES[role]
            os.replace(
                staged_refs / f"{material_id}{suffix}.jpg",
                _MATERIAL_REFS_DIR / f"{material_id}{suffix}.jpg",
            )

        reload_catalog(catalog)
        _set_build_state("pushing", "Zapisano lokalnie. Wysyłam do repozytorium…")
        git = _push_to_repository(
            "Katalog: zapis z panelu Katalog",
            touched=sorted(touched_ids | touched_application_ids)
            + [f"{m}:{r}" for m, r in sorted(touched_view_keys)],
        )
        if git.get("pushed"):
            _set_build_state("ready", "Zapisano i wysłano do repozytorium. Obraz buduje się w CI.")
            message = "Katalog działa już w nowej wersji i jest w repozytorium."
        elif git.get("enabled"):
            _set_build_state("ready", "Zapisano lokalnie; wysyłka do repozytorium czeka na ponowienie.")
            message = "Katalog działa lokalnie, ale zapis do repozytorium się nie udał — ponów z panelu."
        else:
            _set_build_state("ready", "Zapisano i przeładowano katalog (bez wysyłki do repozytorium).")
            message = "Katalog działa już w nowej wersji na tej instancji."
        return {
            "ok": True,
            "message": message,
            "backup": backup_path.name if backup_path else None,
            "git": git,
        }
    except Exception:
        logger.exception("admin catalog transaction failed; restoring previous version")
        try:
            temp_catalog.unlink(missing_ok=True)
            _CATALOG_PATH.write_bytes(old_catalog)
            for material_id in touched_ids:
                for extension in _REFERENCE_EXTENSIONS:
                    (_MATERIAL_REFS_DIR / f"{material_id}{extension}").unlink(missing_ok=True)
                previous = old_references[material_id]
                if previous:
                    suffix, data = previous
                    (_MATERIAL_REFS_DIR / f"{material_id}{suffix}").write_bytes(data)
            for material_id in touched_application_ids:
                for extension in _REFERENCE_EXTENSIONS:
                    (_MATERIAL_REFS_DIR / f"{material_id}-application{extension}").unlink(missing_ok=True)
                previous = old_application_references[material_id]
                if previous:
                    suffix, data = previous
                    (_MATERIAL_REFS_DIR / f"{material_id}-application{suffix}").write_bytes(data)
            for material_id, role in touched_view_keys:
                filename_suffix = _VIEW_REFERENCE_SUFFIXES[role]
                for extension in _REFERENCE_EXTENSIONS:
                    (_MATERIAL_REFS_DIR / f"{material_id}{filename_suffix}{extension}").unlink(
                        missing_ok=True
                    )
                previous = old_view_references[(material_id, role)]
                if previous:
                    suffix, data = previous
                    (_MATERIAL_REFS_DIR / f"{material_id}{filename_suffix}{suffix}").write_bytes(data)
            reload_catalog(json.loads(old_catalog))
        except Exception:
            logger.exception("admin catalog rollback failed")
        raise
    finally:
        shutil.rmtree(staging_parent, ignore_errors=True)


def _push_to_repository(message: str, touched: list[str] | None = None) -> dict:
    """Commit the runtime catalogue to GitHub. Never raises: a failure is
    recorded in pending-push.json (and reported) so the local edit survives
    and can be retried; a success clears it and records last-push.json."""
    cfg = load_git_config()
    if not cfg.enabled and not _PERSIST_RUNTIME_CATALOG:
        # Source mode: the save landed in the git working tree; the developer
        # commits it with git. Nothing is pending and nothing can be lost.
        return {"enabled": False, "pushed": False, "pending": None, "mode": "source"}
    if not cfg.enabled:
        # No token: edits stay local. Record that so a new image does not
        # overwrite them on the next start (see paths._seed_runtime_catalog).
        write_json(_PENDING_PUSH_PATH, {
            "since": int(time.time()),
            "reason": "not_configured",
            "message": "Brak CATALOG_GIT_TOKEN — edycje są tylko na tej instancji.",
            "touched": touched or [],
        })
        return {"enabled": False, "pushed": False, "pending": read_json(_PENDING_PUSH_PATH)}
    pending_before = read_json(_PENDING_PUSH_PATH)
    try:
        result = push_catalog(
            catalog_bytes=_CATALOG_PATH.read_bytes(),
            references_dir=_MATERIAL_REFS_DIR,
            message=message,
            cfg=cfg,
        )
    except CatalogGitError as exc:
        logger.warning("catalog git push failed: %s (%s)", exc.message, exc.detail)
        write_json(_PENDING_PUSH_PATH, {
            "since": (pending_before or {}).get("since") or int(time.time()),
            "last_attempt": int(time.time()),
            "reason": "push_failed",
            "retryable": exc.retryable,
            "message": exc.message,
            "detail": exc.detail,
            "touched": sorted(set((pending_before or {}).get("touched", []) + (touched or []))),
        })
        return {"enabled": True, "pushed": False, "error": exc.message, "retryable": exc.retryable,
                "pending": read_json(_PENDING_PUSH_PATH)}
    _PENDING_PUSH_PATH.unlink(missing_ok=True)
    record = {
        "sha": result["sha"],
        "url": result["url"],
        "at": int(time.time()),
        "files_changed": result["files_changed"],
        "noop": result.get("noop", False),
        "branch": cfg.branch,
        "repo": cfg.repo,
    }
    write_json(_LAST_PUSH_PATH, record)
    return {"enabled": True, "pushed": True, **record, "pending": None}


def _git_state() -> dict:
    cfg = load_git_config()
    return {
        **cfg.public(),
        "mode": "docker" if _PERSIST_RUNTIME_CATALOG else "source",
        "pending": read_json(_PENDING_PUSH_PATH),
        "last_push": read_json(_LAST_PUSH_PATH),
        "build_sha": os.environ.get("NANO_SOFA_BUILD_SHA", "") or None,
    }


def _admin_payload() -> dict:
    references = {}
    application_references = {}
    view_references = {}
    for material in CATALOG["materials"]:
        material_id = material["id"]
        path = _reference_path(material_id)
        references[material_id] = {
            "exists": bool(path),
            "filename": path.name if path else None,
            "url": (
                f"/api/admin/material-reference/{material_id}?v={path.stat().st_mtime_ns}"
                if path else None
            ),
        }
        application_path = _application_reference_path(material_id)
        application_references[material_id] = {
            "exists": bool(application_path),
            "filename": application_path.name if application_path else None,
            "url": (
                f"/api/admin/material-application-reference/{material_id}"
                f"?v={application_path.stat().st_mtime_ns}"
                if application_path else None
            ),
        }
        view_references[material_id] = {}
        for role in _VIEW_REFERENCE_SUFFIXES:
            view_path = _view_reference_path(material_id, role)
            view_references[material_id][role] = {
                "exists": bool(view_path),
                "filename": view_path.name if view_path else None,
                "url": (
                    f"/api/admin/material-view-reference/{role}/{material_id}"
                    f"?v={view_path.stat().st_mtime_ns}"
                    if view_path else None
                ),
            }
    return {
        "catalog": CATALOG,
        "color_index": flatten_colors(CATALOG),
        "references": references,
        "application_references": application_references,
        "view_references": view_references,
        "build": dict(_BUILD_STATE),
        "git": _git_state(),
        "known_tex": _KNOWN_TEX,
        "catalog_updated_at": int(_CATALOG_PATH.stat().st_mtime),
    }


@router.get("/admin")
def admin_page():
    # The page itself is static; every API call behind it is gated.
    return page_response("admin.html")


@router.get("/api/admin/catalog")
def get_admin_catalog(request: Request):
    _require_admin(request)
    return _admin_payload()


@router.get("/api/admin/status")
def admin_status(request: Request):
    _require_admin(request)
    return {**_BUILD_STATE, "git": _git_state()}


@router.get("/api/admin/build-status")
def admin_build_status(request: Request, sha: str = ""):
    """CI state for a commit made by the panel (defaults to the last push)."""
    _require_admin(request)
    target = sha.strip() or ((read_json(_LAST_PUSH_PATH) or {}).get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{7,40}", target or ""):
        raise HTTPException(404, "Brak commita do sprawdzenia.")
    return {"sha": target, **workflow_status(target)}


@router.post("/api/admin/retry-push")
async def admin_retry_push(request: Request):
    """Re-send the runtime catalogue to the repository (after a failed push
    or after CATALOG_GIT_TOKEN was configured later)."""
    _require_admin(request)
    if _SAVE_LOCK.locked():
        raise HTTPException(409, "Inny zapis katalogu jest już w toku.")
    async with _SAVE_LOCK:
        _set_build_state("pushing", "Wysyłam katalog do repozytorium…")
        git = await asyncio.to_thread(_push_to_repository, "Katalog: ponowna wysyłka z panelu Katalog")
        if git.get("pushed"):
            _set_build_state("ready", "Wysłano do repozytorium. Obraz buduje się w CI.")
        elif git.get("enabled"):
            _set_build_state("error", git.get("error") or "Wysyłka nie powiodła się.")
        else:
            _set_build_state("ready", "Brak CATALOG_GIT_TOKEN — nic nie wysłano.")
        return {"git": git, "build": dict(_BUILD_STATE)}


@router.get("/api/admin/material-reference/{material_id}")
def material_reference(material_id: str, request: Request):
    _require_admin(request)
    if not _ID_RE.fullmatch(material_id):
        raise HTTPException(404, "Nie znaleziono referencji.")
    path = _reference_path(material_id)
    if not path:
        raise HTTPException(404, "Nie znaleziono referencji.")
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.get("/api/admin/material-application-reference/{material_id}")
def material_application_reference(material_id: str, request: Request):
    _require_admin(request)
    if not _ID_RE.fullmatch(material_id):
        raise HTTPException(404, "Nie znaleziono referencji na meblu.")
    path = _application_reference_path(material_id)
    if not path:
        raise HTTPException(404, "Nie znaleziono referencji na meblu.")
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.get("/api/admin/material-view-reference/{role}/{material_id}")
def material_view_reference(role: str, material_id: str, request: Request):
    _require_admin(request)
    if not _ID_RE.fullmatch(material_id) or role not in _VIEW_REFERENCE_SUFFIXES:
        raise HTTPException(404, "Nie znaleziono dodatkowej referencji materiału.")
    path = _view_reference_path(material_id, role)
    if not path:
        raise HTTPException(404, "Nie znaleziono dodatkowej referencji materiału.")
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.post("/api/admin/catalog")
async def save_admin_catalog(request: Request):
    _require_admin(request)
    if _SAVE_LOCK.locked():
        raise HTTPException(409, "Inny zapis katalogu jest już w toku.")
    async with _SAVE_LOCK:
        try:
            form = await request.form()
            raw_catalog = form.get("catalog_json")
            if not isinstance(raw_catalog, str):
                raise ValueError("Brakuje danych katalogu.")
            catalog = validate_catalog(json.loads(raw_catalog))
            material_ids = {m["id"] for m in catalog["materials"]}

            reference_ids = [str(v) for v in form.getlist("reference_ids")]
            reference_files = form.getlist("reference_files")
            if len(reference_ids) != len(reference_files):
                raise ValueError("Nie udało się powiązać plików referencji z tkaninami.")
            replacements: dict[str, bytes] = {}
            for material_id, upload in zip(reference_ids, reference_files):
                if material_id not in material_ids:
                    raise ValueError(f"Nieznana tkanina referencji: {material_id}")
                if not hasattr(upload, "read"):
                    raise ValueError(f"{material_id}: brak pliku referencji")
                replacements[material_id] = await upload.read()

            raw_deletions = form.get("delete_reference_ids_json", "[]")
            deletions = set(json.loads(str(raw_deletions)))
            if any(not isinstance(v, str) or v not in material_ids for v in deletions):
                raise ValueError("Lista usuwanych referencji zawiera nieznaną tkaninę.")
            deletions -= set(replacements)

            application_reference_ids = [
                str(v) for v in form.getlist("application_reference_ids")
            ]
            application_reference_files = form.getlist("application_reference_files")
            if len(application_reference_ids) != len(application_reference_files):
                raise ValueError(
                    "Nie udało się powiązać referencji na meblach z tkaninami."
                )
            application_replacements: dict[str, bytes] = {}
            for material_id, upload in zip(
                application_reference_ids,
                application_reference_files,
            ):
                if material_id not in material_ids:
                    raise ValueError(
                        f"Nieznana tkanina referencji na meblu: {material_id}"
                    )
                if not hasattr(upload, "read"):
                    raise ValueError(f"{material_id}: brak pliku referencji na meblu")
                application_replacements[material_id] = await upload.read()

            raw_application_deletions = form.get(
                "delete_application_reference_ids_json",
                "[]",
            )
            application_deletions = set(
                json.loads(str(raw_application_deletions))
            )
            if any(
                not isinstance(v, str) or v not in material_ids
                for v in application_deletions
            ):
                raise ValueError(
                    "Lista usuwanych referencji na meblach zawiera nieznaną tkaninę."
                )
            application_deletions -= set(application_replacements)

            view_reference_keys = [
                str(v) for v in form.getlist("view_reference_keys")
            ]
            view_reference_files = form.getlist("view_reference_files")
            if len(view_reference_keys) != len(view_reference_files):
                raise ValueError(
                    "Nie udało się powiązać dodatkowych referencji z tkaninami."
                )
            view_replacements: dict[tuple[str, str], bytes] = {}
            for raw_key, upload in zip(view_reference_keys, view_reference_files):
                material_id, separator, role = raw_key.partition(":")
                if (
                    not separator
                    or material_id not in material_ids
                    or role not in _VIEW_REFERENCE_SUFFIXES
                ):
                    raise ValueError(f"Nieznana dodatkowa referencja: {raw_key}")
                if not hasattr(upload, "read"):
                    raise ValueError(f"{raw_key}: brak pliku referencji")
                view_replacements[(material_id, role)] = await upload.read()

            raw_view_deletions = form.get(
                "delete_view_reference_keys_json",
                "[]",
            )
            view_deletions: set[tuple[str, str]] = set()
            for raw_key in json.loads(str(raw_view_deletions)):
                if not isinstance(raw_key, str):
                    raise ValueError("Nieprawidłowa lista dodatkowych referencji.")
                material_id, separator, role = raw_key.partition(":")
                if (
                    not separator
                    or material_id not in material_ids
                    or role not in _VIEW_REFERENCE_SUFFIXES
                ):
                    raise ValueError(f"Nieznana usuwana referencja: {raw_key}")
                view_deletions.add((material_id, role))
            view_deletions -= set(view_replacements)

            _set_build_state("validating", "Sprawdzam katalog i referencje…")
            result = await asyncio.to_thread(
                _commit_update,
                catalog,
                replacements,
                deletions,
                application_replacements,
                application_deletions,
                view_replacements,
                view_deletions,
            )
            return {**result, **_admin_payload()}
        except json.JSONDecodeError as exc:
            _set_build_state("error", "Nieprawidłowy format danych.")
            raise HTTPException(400, "Nieprawidłowy JSON katalogu.") from exc
        except ValueError as exc:
            _set_build_state("error", str(exc))
            raise HTTPException(422, str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            _set_build_state("error", str(exc))
            raise HTTPException(500, f"Nie udało się zapisać katalogu. Przywrócono poprzednią wersję. {exc}") from exc
