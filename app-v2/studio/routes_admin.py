"""Local catalogue administration with validation, build and rollback.

This surface is intentionally available only from a loopback browser.  A save
is a transaction: validate the catalogue and images, build the frontend into a
staging directory, snapshot the old files, promote the new files, then refresh
the stable in-memory catalogue dictionaries.  A failure restores the previous
working version.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from studio.catalog import CATALOG, _CATALOG_PATH, reload_catalog
from studio.paths import (
    _CATALOG_BACKUPS_DIR,
    _DIST_DIR,
    _FRONTEND_DIR,
    _MATERIAL_REFS_DIR,
    logger,
)

router = APIRouter()

_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")
_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_REFERENCE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
_SAVE_LOCK = asyncio.Lock()
_BUILD_STATE: dict = {"state": "idle", "message": "Gotowy", "updated_at": None}


def _require_local(request: Request) -> None:
    """Keep write-capable admin routes private to this computer.

    Checking Origin as well as the socket peer prevents an unrelated website
    open in the browser from posting to localhost while permissive API CORS is
    enabled for the development frontend.
    """
    client_host = request.client.host if request.client else ""
    local_hosts = {"127.0.0.1", "::1", "localhost", "testclient"}
    if client_host not in local_hosts:
        raise HTTPException(403, "Panel administracyjny działa tylko lokalnie.")
    origin = request.headers.get("origin")
    if origin:
        origin_host = (urlparse(origin).hostname or "").lower()
        if origin_host not in {"127.0.0.1", "::1", "localhost"}:
            raise HTTPException(403, "Nieprawidłowe źródło żądania administracyjnego.")


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

    result = dict(payload)
    result["materials"] = normalized_materials
    result["colors"] = normalized_colors
    return result


def _reference_path(material_id: str) -> Path | None:
    for extension in _REFERENCE_EXTENSIONS:
        candidate = _MATERIAL_REFS_DIR / f"{material_id}{extension}"
        if candidate.is_file():
            return candidate
    return None


def _prepare_reference(data: bytes, material_id: str, target_dir: Path) -> Path:
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
            if image.width > 4096 or image.height > 4096:
                image.thumbnail((4096, 4096), Image.Resampling.LANCZOS)
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            destination = target_dir / f"{material_id}.png"
            image.save(destination, format="PNG", optimize=True)
            return destination
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"{material_id}: plik nie jest poprawnym obrazem") from exc


def _set_build_state(state: str, message: str) -> None:
    _BUILD_STATE.update({"state": state, "message": message, "updated_at": int(time.time())})


def _build_frontend(staging_dist: Path) -> str:
    vite = _FRONTEND_DIR / "node_modules" / ".bin" / "vite"
    if not vite.is_file():
        raise RuntimeError(
            "Brakuje zależności frontendu. Uruchom raz: cd app-v2/frontend && npm install"
        )
    process = subprocess.run(
        [str(vite), "build", "--outDir", str(staging_dist), "--emptyOutDir"],
        cwd=_FRONTEND_DIR,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    build_log = "\n".join(part.strip() for part in (process.stdout, process.stderr) if part.strip())
    if process.returncode != 0:
        raise RuntimeError("Build frontendu nie powiódł się.\n" + build_log[-4000:])
    if not (staging_dist / "index.html").is_file() or not (staging_dist / "admin.html").is_file():
        raise RuntimeError("Build zakończył się bez wymaganych stron index.html/admin.html.")
    return build_log[-2000:]


def _write_backup(old_catalog: bytes, touched_ids: set[str]) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    destination = _CATALOG_BACKUPS_DIR / f"catalog-{timestamp}-{time.time_ns() % 1_000_000:06d}.zip"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("catalog.json", old_catalog)
        manifest: dict[str, str | None] = {}
        for material_id in sorted(touched_ids):
            path = _reference_path(material_id)
            manifest[material_id] = path.name if path else None
            if path:
                archive.write(path, f"material-references/{path.name}")
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    backups = sorted(_CATALOG_BACKUPS_DIR.glob("catalog-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in backups[10:]:
        stale.unlink(missing_ok=True)
    return destination


def _commit_update(catalog: dict, replacements: dict[str, bytes], deletions: set[str]) -> dict:
    old_catalog = _CATALOG_PATH.read_bytes()
    touched_ids = set(replacements) | set(deletions)
    old_references: dict[str, tuple[str, bytes] | None] = {}
    for material_id in touched_ids:
        existing = _reference_path(material_id)
        old_references[material_id] = (existing.suffix, existing.read_bytes()) if existing else None

    _MATERIAL_REFS_DIR.mkdir(parents=True, exist_ok=True)
    staging_parent = Path(tempfile.mkdtemp(prefix=".admin-build-", dir=_FRONTEND_DIR))
    staging_dist = staging_parent / "dist"
    staged_refs = staging_parent / "references"
    staged_refs.mkdir()
    old_dist = _FRONTEND_DIR / ".dist-before-admin-save"
    temp_catalog = _CATALOG_PATH.with_suffix(".json.admin-tmp")
    promoted_dist = False
    backup_path: Path | None = None
    try:
        for material_id, data in replacements.items():
            _prepare_reference(data, material_id, staged_refs)

        _set_build_state("building", "Walidacja zakończona. Przebudowuję aplikację…")
        build_log = _build_frontend(staging_dist)
        backup_path = _write_backup(old_catalog, touched_ids)

        temp_catalog.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if old_dist.exists():
            shutil.rmtree(old_dist)
        os.replace(_DIST_DIR, old_dist)
        os.replace(staging_dist, _DIST_DIR)
        promoted_dist = True
        os.replace(temp_catalog, _CATALOG_PATH)

        for material_id in touched_ids:
            for extension in _REFERENCE_EXTENSIONS:
                (_MATERIAL_REFS_DIR / f"{material_id}{extension}").unlink(missing_ok=True)
        for material_id in replacements:
            os.replace(staged_refs / f"{material_id}.png", _MATERIAL_REFS_DIR / f"{material_id}.png")

        reload_catalog(catalog)
        shutil.rmtree(old_dist, ignore_errors=True)
        _set_build_state("ready", "Zapisano, przebudowano i przeładowano katalog.")
        return {
            "ok": True,
            "message": "Katalog działa już w nowej wersji.",
            "backup": backup_path.name if backup_path else None,
            "build_log": build_log,
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
            if promoted_dist:
                shutil.rmtree(_DIST_DIR, ignore_errors=True)
                if old_dist.exists():
                    os.replace(old_dist, _DIST_DIR)
            reload_catalog(json.loads(old_catalog))
        except Exception:
            logger.exception("admin catalog rollback failed")
        raise
    finally:
        shutil.rmtree(staging_parent, ignore_errors=True)


def _admin_payload() -> dict:
    references = {}
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
    return {
        "catalog": CATALOG,
        "references": references,
        "build": dict(_BUILD_STATE),
        "catalog_updated_at": int(_CATALOG_PATH.stat().st_mtime),
    }


@router.get("/admin")
def admin_page(request: Request):
    _require_local(request)
    return FileResponse(_DIST_DIR / "admin.html")


@router.get("/api/admin/catalog")
def get_admin_catalog(request: Request):
    _require_local(request)
    return _admin_payload()


@router.get("/api/admin/status")
def admin_status(request: Request):
    _require_local(request)
    return dict(_BUILD_STATE)


@router.get("/api/admin/material-reference/{material_id}")
def material_reference(material_id: str, request: Request):
    _require_local(request)
    if not _ID_RE.fullmatch(material_id):
        raise HTTPException(404, "Nie znaleziono referencji.")
    path = _reference_path(material_id)
    if not path:
        raise HTTPException(404, "Nie znaleziono referencji.")
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.post("/api/admin/catalog")
async def save_admin_catalog(request: Request):
    _require_local(request)
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

            _set_build_state("validating", "Sprawdzam katalog i referencje…")
            result = await asyncio.to_thread(_commit_update, catalog, replacements, deletions)
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
