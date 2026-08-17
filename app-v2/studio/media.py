"""Image upload decode/save, delivery-format derivation, EXIF identity
stamping, PNG metadata reads, anchor resolution, and storage retention."""

from __future__ import annotations

import asyncio
import io
import json
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import UploadFile
from PIL import Image

from app.core.cost_tracker import output_path_for_generation
from studio.paths import _OUTPUT_DIR, _UPLOAD_DIR, logger


def _decode_and_save(raw: bytes, suffix: str) -> Path:
    """CPU-bound PIL decode/encode. Runs in a worker thread, never on the loop."""
    pil = Image.open(io.BytesIO(raw))
    pil.load()
    out = _UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}.png"
    pil.convert("RGB").save(out, format="PNG")
    return out


async def _save_upload(upload: UploadFile, suffix: str = "") -> Path:
    """Read an UploadFile, decode as image, save as PNG under the uploads dir.

    The blocking PIL decode/encode is off-loaded to a thread so a large upload
    can't stall the event loop (and with it /healthz and every other request).
    """
    raw = await upload.read()
    return await asyncio.to_thread(_decode_and_save, raw, suffix)


# ---------------------------------------------------------------------------
# Output format / size optimization
# ---------------------------------------------------------------------------
# Envs that emit a transparent-background render (alpha). JPEG can't hold alpha,
# so a JPG request for these is downgraded to WebP (which keeps alpha + stays
# small). Source of truth: the transparent cyclorama profile in _ENV_TO_SCENE.
_TRANSPARENT_ENVS = {"cyclorama_transparent", "transparent"}

_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
    ".mp4": "video/mp4", ".webm": "video/webm",
}


def _parse_quality(raw: str, default: int = 82) -> int:
    """Clamp a user-supplied quality string to a sane JPEG/WebP range."""
    try:
        q = int(float(raw))
    except (TypeError, ValueError):
        return default
    return max(40, min(100, q))


def _exif_bytes_from_png(img: Image.Image) -> Optional[bytes]:
    """Pack a master PNG's nano_sofa_* tEXt metadata into an EXIF block so the
    identity survives into the delivered JPEG/WebP (PNG text chunks don't carry
    over to those formats). Stored as compact JSON in ImageDescription (0x010E),
    with Software (0x0131) as a marker. Returns None when the master has no id."""
    text = getattr(img, "text", None) or {}
    gid = text.get("nano_sofa_generation_id")
    if not gid:
        return None
    payload = {
        "generation_id": gid,
        "model": text.get("nano_sofa_model", ""),
        "resolution": text.get("nano_sofa_resolution", ""),
        "color": text.get("nano_sofa_color", ""),
        "material": text.get("nano_sofa_material", ""),
        "summary": text.get("nano_sofa_prompt_summary", ""),
    }
    exif = Image.Exif()
    exif[0x010E] = "nano-sofa " + json.dumps(payload, ensure_ascii=False)
    exif[0x0131] = "Nano Sofa Studio v2"
    try:
        return exif.tobytes()
    except Exception:
        return None


def _derive_output(master: Path, fmt: str, quality: int, transparent: bool) -> tuple[Path, str, bool]:
    """
    From the lossless PNG `master`, write the user-facing delivery file in
    `fmt` (jpg|png|webp) and return (path, fmt_used, downgraded).

    The master is never mutated — it stays the lossless reference used by the
    variant/photoshoot pixel-lock chain. For png we just serve the master.
    JPEG has no alpha, so a transparent render asked for as jpg is transparently
    downgraded to WebP (keeps alpha, still ~5x smaller than PNG).
    """
    fmt = (fmt or "jpg").lower().strip()
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt not in ("jpg", "png", "webp"):
        fmt = "jpg"

    downgraded = False
    if fmt == "jpg" and transparent:
        fmt = "webp"
        downgraded = True

    if fmt == "png":
        return master, "png", False  # master is already an optimized PNG

    img = Image.open(master)
    img.load()
    # Carry the master's embedded id into the delivery file (EXIF) so downloads
    # and re-imports stay identifiable. Read before any mode conversion below.
    meta_exif = _exif_bytes_from_png(img)
    save_kwargs = {"exif": meta_exif} if meta_exif else {}
    out = master.with_suffix("." + fmt)
    if fmt == "jpg":
        # Flatten any alpha onto white before JPEG (no alpha channel in JPEG).
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            img = bg
        img.convert("RGB").save(out, format="JPEG", quality=quality, optimize=True, progressive=True, **save_kwargs)
    else:  # webp — keeps alpha if present
        img.save(out, format="WEBP", quality=quality, method=6, **save_kwargs)
    return out, fmt, downgraded


async def _derived_url(master: Path, fmt: str, quality: int, transparent: bool) -> tuple[str, str, bool]:
    """Derive the delivery file off the event loop and return its public URL."""
    derived, fmt_used, downgraded = await asyncio.to_thread(
        _derive_output, master, fmt, quality, transparent
    )
    return f"/api/outputs/{derived.name}", fmt_used, downgraded


# ---------------------------------------------------------------------------
# Storage retention — keep the outputs volume from growing without bound. Best
# effort: never raises, never blocks a response (run via asyncio.to_thread).
# ---------------------------------------------------------------------------
_MAX_OUTPUT_FILES = int(os.environ.get("MAX_OUTPUT_FILES", "800"))
_MAX_UPLOAD_FILES = int(os.environ.get("MAX_UPLOAD_FILES", "200"))


def _prune_dir(directory: Path, keep_newest: int) -> int:
    try:
        files = [p for p in directory.iterdir() if p.is_file()]
    except Exception:
        return 0
    if len(files) <= keep_newest:
        return 0
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for p in files[keep_newest:]:
        try:
            p.unlink()
            removed += 1
        except Exception:
            pass
    return removed


def _prune_storage() -> None:
    """Trim outputs + uploads to their newest-N caps. Masters and their derived
    siblings share an mtime, so they prune together."""
    try:
        n_out = _prune_dir(_OUTPUT_DIR, _MAX_OUTPUT_FILES)
        n_up = _prune_dir(_UPLOAD_DIR, _MAX_UPLOAD_FILES)
        if n_out or n_up:
            logger.info("Storage prune: removed %d output(s), %d upload(s)", n_out, n_up)
    except Exception as exc:  # never let cleanup break a request
        logger.warning("Storage prune skipped: %s", exc)


def _read_png_meta(path: Path) -> dict:
    """Read the nano_sofa_* tEXt chunks off a master PNG, best-effort."""
    try:
        with Image.open(path) as im:
            return dict(getattr(im, "text", {}) or {})
    except Exception:
        return {}


def _resolve_anchor_path(anchor_ref: str) -> Optional[Path]:
    """Resolve a client-supplied anchor reference to an on-disk master image.

    `anchor_ref` may be a full generation_id OR an /api/outputs basename (which
    can be a derived .jpg/.webp). Returns the lossless .png master when present
    (preferred for the pixel-lock), else the referenced file. Always constrained
    to _OUTPUT_DIR by basename — no path traversal, no client-supplied dirs.
    """
    ref = (anchor_ref or "").strip()
    if not ref:
        return None

    # 1. generation_id → look up the master in the cost DB, then re-home its
    # basename into _OUTPUT_DIR (the DB may hold a path from the v1 layout).
    db_path = output_path_for_generation(ref)
    if db_path:
        cand = (_OUTPUT_DIR / Path(db_path).name).resolve()
        if cand.parent == _OUTPUT_DIR and cand.is_file():
            return cand

    # 2. looks like a generation_id (uuid, no dot/slash) → match the filename
    # convention {ts}_{model}_{id[:8]}.png directly on disk, so a render still
    # resolves even when the DB has no row for it (stale/foreign DB).
    if "." not in ref and "/" not in ref and len(ref) >= 8:
        for cand in sorted(_OUTPUT_DIR.glob(f"*_{ref[:8]}.png")):
            cand = cand.resolve()
            if cand.parent == _OUTPUT_DIR and cand.is_file():
                return cand

    # 3. basename → prefer the .png master over a .jpg/.webp derivative.
    name = Path(ref).name
    for cand in (_OUTPUT_DIR / f"{Path(name).stem}.png", _OUTPUT_DIR / name):
        cand = cand.resolve()
        if cand.parent == _OUTPUT_DIR and cand.is_file():
            return cand
    return None
