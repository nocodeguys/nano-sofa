#!/usr/bin/env python3
"""Measure an eval run (scripts/eval_matrix.py) and compare two runs.

Metrics per render — all plain numpy + PIL, no model in the loop:

  upholstery_de     ΔE2000 between the target hex and the dominant colour
                    cluster of the product that is closest to the target.
                    "Closest cluster" is deliberate: a bed is upholstery +
                    white bedding + shadow, and we want the fabric, not the
                    average. upholstery_share says how much of the product
                    that cluster covers (small share = the colour is barely
                    there).
  product_width_share, product_height_share
                    bounding box of the product mask over the frame. The
                    catalog contract asks a hero to span 78–84 % of the width.
  mask_share        product pixels / frame. Close-ups and macro crops should
                    fill the frame; a hero should not.
  backdrop_de       ΔE2000 between the expected backdrop hex (catalog runs)
                    and the median colour of the frame border.

The product mask is "everything that is not the backdrop": pixels farther
than a ΔE threshold from the border colour, cleaned with an open/close. It
is honest for packshots and only indicative for lifestyle scenes (the
border is not a backdrop there — backdrop_known=false in the output).

Usage:
    .venv/bin/python scripts/eval_report.py report  outputs/eval/<run>
    .venv/bin/python scripts/eval_report.py compare outputs/eval/<runA> outputs/eval/<runB>
    .venv/bin/python scripts/eval_report.py image   some.png --hex "#938A83" [--backdrop "#F7F5F1"]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image, ImageFilter

# --------------------------------------------------------------------------
# Colour science: sRGB → CIELAB (D65) and ΔE2000. Vectorised over (..., 3).
# --------------------------------------------------------------------------
_M_RGB_TO_XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
])
_D65 = np.array([0.95047, 1.00000, 1.08883])


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """rgb in 0..255, shape (..., 3) → Lab, shape (..., 3)."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = lin @ _M_RGB_TO_XYZ.T / _D65
    eps, kappa = 216 / 24389, 24389 / 27
    f = np.where(xyz > eps, np.cbrt(xyz), (kappa * xyz + 16) / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def delta_e2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """CIEDE2000 (Sharma et al. 2005), broadcasting over leading dims."""
    lab1 = np.asarray(lab1, dtype=np.float64)
    lab2 = np.asarray(lab2, dtype=np.float64)
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cbar**7 / (Cbar**7 + 25.0**7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp = L2 - L1
    dCp = C2p - C1p
    dh = h2p - h1p
    dhp = np.where(C1p * C2p == 0, 0.0,
                   np.where(np.abs(dh) <= 180, dh, np.where(dh > 180, dh - 360, dh + 360)))
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp / 2))
    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    hsum = h1p + h2p
    hbp = np.where(C1p * C2p == 0, hsum,
                   np.where(np.abs(h1p - h2p) <= 180, hsum / 2,
                            np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dtheta = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    RC = 2 * np.sqrt(Cbp**7 / (Cbp**7 + 25.0**7))
    SL = 1 + (0.015 * (Lbp - 50) ** 2) / np.sqrt(20 + (Lbp - 50) ** 2)
    SC = 1 + 0.045 * Cbp
    SH = 1 + 0.015 * Cbp * T
    RT = -np.sin(np.radians(2 * dtheta)) * RC
    return np.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2
                   + RT * (dCp / SC) * (dHp / SH))


def hex_to_rgb(value: str) -> Optional[np.ndarray]:
    v = (value or "").strip().lstrip("#")
    if len(v) != 6:
        return None
    return np.array([int(v[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)


def rgb_to_hex(rgb) -> str:
    r, g, b = (int(round(float(x))) for x in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


# --------------------------------------------------------------------------
# Image metrics
# --------------------------------------------------------------------------
MASK_DE_THRESHOLD = 5.0      # pixel is "product" if this far from the backdrop
BORDER_FRAC = 0.06           # border band used to estimate the backdrop
MAX_SIDE = 512               # analysis resolution


def _load_rgb(path: Path) -> np.ndarray:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = min(1.0, MAX_SIDE / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    return np.asarray(img, dtype=np.float64)


def _border_median(rgb: np.ndarray) -> np.ndarray:
    h, w, _ = rgb.shape
    bh, bw = max(1, int(h * BORDER_FRAC)), max(1, int(w * BORDER_FRAC))
    band = np.concatenate([
        rgb[:bh].reshape(-1, 3), rgb[:, :bw].reshape(-1, 3), rgb[:, -bw:].reshape(-1, 3),
    ])
    return np.median(band, axis=0)


def _product_mask(lab: np.ndarray, backdrop_lab: np.ndarray) -> np.ndarray:
    de = delta_e2000(lab, backdrop_lab[None, None, :])
    raw = (de > MASK_DE_THRESHOLD).astype(np.uint8) * 255
    m = Image.fromarray(raw, mode="L")
    m = m.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))   # open
    m = m.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))   # close
    return np.asarray(m) > 127


def _bbox_share(mask: np.ndarray) -> tuple[float, float]:
    h, w = mask.shape
    rows = mask.sum(axis=1) > max(2, 0.005 * w)
    cols = mask.sum(axis=0) > max(2, 0.005 * h)
    if not rows.any() or not cols.any():
        return 0.0, 0.0
    r = np.flatnonzero(rows)
    c = np.flatnonzero(cols)
    return float((c[-1] - c[0] + 1) / w), float((r[-1] - r[0] + 1) / h)


def _kmeans(points: np.ndarray, k: int = 5, iters: int = 20, seed: int = 7):
    rng = np.random.default_rng(seed)
    n = len(points)
    if n == 0:
        return np.zeros((0, 3)), np.zeros(0, dtype=int)
    k = min(k, n)
    # k-means++ seeding, plain Lloyd iterations.
    centers = [points[rng.integers(n)]]
    for _ in range(1, k):
        d2 = np.min(((points[:, None, :] - np.array(centers)[None, :, :]) ** 2).sum(-1), axis=1)
        probs = d2 / d2.sum() if d2.sum() > 0 else np.full(n, 1 / n)
        centers.append(points[rng.choice(n, p=probs)])
    centers = np.array(centers)
    labels = np.zeros(n, dtype=int)
    for _ in range(iters):
        d2 = ((points[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
        new_labels = d2.argmin(axis=1)
        if np.array_equal(new_labels, labels) and _ > 0:
            break
        labels = new_labels
        for j in range(k):
            sel = points[labels == j]
            if len(sel):
                centers[j] = sel.mean(axis=0)
    return centers, labels


def measure(path: Path, target_hex: str, backdrop_hex: str = "") -> dict[str, Any]:
    rgb = _load_rgb(path)
    lab = srgb_to_lab(rgb)
    h, w, _ = rgb.shape

    border_rgb = _border_median(rgb)
    border_lab = srgb_to_lab(border_rgb)
    out: dict[str, Any] = {
        "size": [int(w), int(h)],
        "border_hex": rgb_to_hex(border_rgb),
        "backdrop_known": bool(hex_to_rgb(backdrop_hex) is not None),
    }
    expected_bd = hex_to_rgb(backdrop_hex)
    if expected_bd is not None:
        out["backdrop_de"] = round(float(delta_e2000(border_lab, srgb_to_lab(expected_bd))), 2)

    mask = _product_mask(lab, border_lab)
    out["mask_share"] = round(float(mask.mean()), 3)
    ws, hs = _bbox_share(mask)
    out["product_width_share"] = round(ws, 3)
    out["product_height_share"] = round(hs, 3)

    target = hex_to_rgb(target_hex)
    pts_lab = lab[mask]
    pts_rgb = rgb[mask]
    if target is not None and len(pts_lab) >= 50:
        rng = np.random.default_rng(1)
        if len(pts_lab) > 20000:
            idx = rng.choice(len(pts_lab), 20000, replace=False)
            pts_lab, pts_rgb = pts_lab[idx], pts_rgb[idx]
        centers, labels = _kmeans(pts_lab)
        target_lab = srgb_to_lab(target)
        des = delta_e2000(centers, target_lab[None, :])
        j = int(des.argmin())
        share = float((labels == j).mean())
        # Report the cluster as the mean sRGB of its own pixels (same sample
        # as the labels), which is what a person would eyedrop.
        cluster_rgb = pts_rgb[labels == j].mean(axis=0) if (labels == j).any() else target
        out.update({
            "upholstery_de": round(float(des[j]), 2),
            "upholstery_share": round(share, 3),
            "upholstery_hex": rgb_to_hex(cluster_rgb),
            "target_hex": target_hex.upper(),
        })
    return out


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
def _check(value: Optional[float], rng: Optional[list[float]]) -> str:
    if value is None or not rng:
        return ""
    lo, hi = rng
    return "✓" if lo <= value <= hi else "✗"


def _fmt(v: Any, nd: int = 2) -> str:
    if v is None or v == "":
        return "–"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def report(run_dir: Path) -> Path:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    rows = []
    for case in manifest["cases"]:
        row = {k: case.get(k) for k in ("id", "kind", "mode", "shot", "n_refs", "cost", "elapsed_ms", "error")}
        row["camera_offset_pct"] = (case.get("prompt_stats") or {}).get("camera_offset_pct")
        if case.get("file"):
            m = measure(run_dir / case["file"], case.get("upholstery_hex", ""), case.get("backdrop_hex", ""))
            row.update(m)
            exp = case.get("expect") or {}
            row["framing_ok"] = (_check(m.get("product_width_share"), exp.get("product_width_share"))
                                 or _check(m.get("mask_share"), exp.get("mask_share")))
            row["backdrop_ok"] = _check(m.get("backdrop_de"), [0, 3.0]) if m.get("backdrop_known") else ""
        rows.append(row)

    (run_dir / "metrics.json").write_text(json.dumps(
        {"run": manifest["run"], "model": manifest["model"], "git_sha": manifest.get("git_sha", ""),
         "rows": rows}, indent=2, ensure_ascii=False))

    lines = [
        f"# Eval report — {manifest['run']}",
        "",
        f"model `{manifest['model']}` · engine {manifest['engine']} · quality {manifest.get('quality') or '–'}"
        f" · git {manifest.get('git_sha') or '–'} · total ${manifest.get('total_cost', 0):.4f}",
        "",
        "| case | refs | cam@% | uph ΔE | uph share | uph hex | width | mask | bd ΔE | framing | backdrop | cost | ms | error |",
        "|---|---:|---:|---:|---:|---|---:|---:|---:|:-:|:-:|---:|---:|---|",
    ]
    for r in rows:
        lines.append("| " + " | ".join([
            r["id"], _fmt(r.get("n_refs")), _fmt(r.get("camera_offset_pct")),
            _fmt(r.get("upholstery_de")), _fmt(r.get("upholstery_share")), _fmt(r.get("upholstery_hex")),
            _fmt(r.get("product_width_share")), _fmt(r.get("mask_share")), _fmt(r.get("backdrop_de")),
            r.get("framing_ok") or "", r.get("backdrop_ok") or "",
            _fmt(r.get("cost"), 4), _fmt(r.get("elapsed_ms")), (r.get("error") or "")[:60],
        ]) + " |")
    lines += [
        "",
        "Legend: uph ΔE = CIEDE2000 of the product's dominant colour cluster nearest the target hex"
        " (≤ 3 indistinguishable, ≤ 6 close, > 10 visibly off); width = product bbox / frame width"
        " (hero contract 0.78–0.84); mask = product pixels / frame (close-up ≥ 0.6, macro ≥ 0.9);"
        " bd ΔE = border colour vs expected backdrop (catalog only).",
    ]
    out = run_dir / "report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return out


def compare(run_a: Path, run_b: Path) -> Path:
    ma = json.loads((run_a / "metrics.json").read_text())
    mb = json.loads((run_b / "metrics.json").read_text())
    ra = {r["id"]: r for r in ma["rows"]}
    rb = {r["id"]: r for r in mb["rows"]}
    keys = ("upholstery_de", "upholstery_share", "product_width_share", "mask_share", "backdrop_de")
    lines = [
        f"# Compare — A: {ma['run']} ({ma['model']}, {ma.get('git_sha', '')})"
        f" vs B: {mb['run']} ({mb['model']}, {mb.get('git_sha', '')})",
        "",
        "| case | " + " | ".join(f"{k} A | B | Δ" for k in keys) + " |",
        "|---|" + "---:|---:|---:|" * len(keys),
    ]
    for cid in sorted(set(ra) | set(rb)):
        a, b = ra.get(cid, {}), rb.get(cid, {})
        cells = [cid]
        for k in keys:
            va, vb = a.get(k), b.get(k)
            d = (vb - va) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None
            cells += [_fmt(va), _fmt(vb), (f"{d:+.2f}" if d is not None else "–")]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "Δ = B − A. For ΔE lower is better; for width/mask compare against the contract, not against A."]
    out = run_b / f"compare-{ma['run']}-vs-{mb['run']}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("report"); p.add_argument("run", type=Path)
    p = sub.add_parser("compare"); p.add_argument("run_a", type=Path); p.add_argument("run_b", type=Path)
    p = sub.add_parser("image"); p.add_argument("path", type=Path)
    p.add_argument("--hex", required=True); p.add_argument("--backdrop", default="")
    args = ap.parse_args()
    if args.cmd == "report":
        report(args.run)
    elif args.cmd == "compare":
        compare(args.run_a, args.run_b)
    else:
        print(json.dumps(measure(args.path, args.hex, args.backdrop), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
