#!/usr/bin/env python3
"""
Bake-off: Seedream 4.5 + FLUX.2 pro vs Gemini 2.5 Flash Image (baseline),
all through the OpenRouter Images API, using EXACTLY the prompts the app
builds (studio.request_builder + app.core.generator._build_prompt_text) and
the same base product photo as the single image reference.

Usage:
    OPENROUTER_API_KEY=sk-or-... .venv/bin/python scripts/bakeoff_openrouter.py
    .venv/bin/python scripts/bakeoff_openrouter.py --dry-run      # no API calls
    ... --models google/gemini-3-pro-image ...                    # extend the field

Output: outputs/bakeoff/<run>/  — one image per (case, model), results.json
with per-image cost as reported by OpenRouter, and index.html — a side-by-side
gallery (base | model columns) for eyeballing geometry and fabric fidelity.

Docs: https://openrouter.ai/docs/features/multimodal/image-generation
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "app-v2"))

from studio.request_builder import _build_generation_request  # noqa: E402
from studio.mappings import _compose_bedding_description  # noqa: E402
from app.core.generator import _build_prompt_text  # noqa: E402

# ── Base product photos (existing uploads) ──────────────────────────────────
BED_CHANNEL = REPO_ROOT / "outputs/v2-uploads/02841ec18b384dda92fbf8db36e5f286.png"
BED_BUBBLE = REPO_ROOT / "outputs/v2-uploads/7c80cd4ce5ff40669c0c04e3170b45b7.png"

# ── Models under test ───────────────────────────────────────────────────────
DEFAULT_MODELS = {
    "gemini": "google/gemini-2.5-flash-image",   # baseline — what the app uses today
    "seedream": "bytedance-seed/seedream-4.5",
    "flux": "black-forest-labs/flux.2-pro",
}
# Per-endpoint quirks (verified via /api/v1/images/models/{slug}/endpoints):
#  - seedream supports `resolution` (1K/2K/4K); the others do not.
#  - all three support aspect_ratio 3:2 and input_references (3/14/8 max).
SUPPORTS_RESOLUTION = {"bytedance-seed/seedream-4.5"}

ASPECT = "3:2"  # closest to both base photos; identical for every model/case

HOTEL_BEDDING = _compose_bedding_description(
    bedding="linen_white", bedding_custom="", throw="none",
    tidy="hotel", density="minimal", accents_csv="", bed_note="",
)

# ── The matrix ──────────────────────────────────────────────────────────────
# Block 1 (channel-tufted bed): fabric fidelity — all 6 materials, one color.
# Block 2 (same bed): color accuracy on one material (near-white / dark / warm).
# Block 3 (bubble bed): geometry stress, lifestyle scene, bedding restyle.
CASES = [
    # id, base, kind-args
    ("mat-knit",        BED_CHANNEL, dict(mat="knit",        color="greige")),
    ("mat-boucle",      BED_CHANNEL, dict(mat="boucle",      color="greige")),
    ("mat-basketweave", BED_CHANNEL, dict(mat="basketweave", color="greige")),
    ("mat-chenille",    BED_CHANNEL, dict(mat="chenille",    color="greige")),
    ("mat-ecoleather",  BED_CHANNEL, dict(mat="ecoleather",  color="greige")),
    ("mat-velour",      BED_CHANNEL, dict(mat="velour",      color="greige")),
    ("col-pearl",       BED_CHANNEL, dict(mat="boucle",   color="pearl")),
    ("col-forest",      BED_CHANNEL, dict(mat="boucle",   color="forest")),
    ("col-caramel",     BED_CHANNEL, dict(mat="chenille", color="caramel")),
    ("geo-bubble",      BED_BUBBLE,  dict(mat="boucle",   color="caramel")),
    ("scene-japandi",   BED_BUBBLE,  dict(mat="chenille", color="greige",
                                          env="japandi", cam="lounge")),
    ("bedding-hotel",   BED_BUBBLE,  dict(mat="boucle", color="pearl",
                                          bedding=HOTEL_BEDDING)),
]


def build_prompt(base: Path, *, mat: str, color: str,
                 env: str = "cyclorama_neutral", cam: str = "studio",
                 bedding: str = "") -> str:
    req = _build_generation_request(
        api_key="bakeoff", kind="bed",
        color=color, color_custom="",
        mat=mat, mat_notes="",
        size="160", legs="keep",
        cam=cam, lens="50mm_natural", tod="noon_neutral", shadow="soft_diffuse",
        env=env, env_note="", env_mode="",
        model="gemini-2.5-flash-image", aspect=ASPECT, res="1K", seed="",
        base_image_path=base, scene_image_path=None,
        bedding_description=bedding,
    )
    return _build_prompt_text(req)


def data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def generate(client: httpx.Client, model: str, prompt: str, base: Path) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "aspect_ratio": ASPECT,
        "input_references": [
            {"type": "image_url", "image_url": {"url": data_url(base)}},
        ],
    }
    if model in SUPPORTS_RESOLUTION:
        payload["resolution"] = "1K"
    last_err = None
    for attempt in (1, 2):  # one retry on transient failure
        try:
            r = client.post("/images", json=payload, timeout=300)
            if r.status_code >= 500:
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                time.sleep(8 * attempt)
                continue
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            last_err = str(exc)[:200]
            time.sleep(8 * attempt)
    raise RuntimeError(last_err or "unknown error")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print cases + one full prompt, no API calls")
    ap.add_argument("--models", nargs="*", default=None,
                    help="extra OpenRouter model slugs on top of the defaults")
    ap.add_argument("--key", default=os.environ.get("OPENROUTER_API_KEY", ""))
    args = ap.parse_args()

    models = dict(DEFAULT_MODELS)
    for slug in args.models or []:
        models[slug.rsplit("/", 1)[-1]] = slug

    run_dir = REPO_ROOT / "outputs" / "bakeoff" / time.strftime("%Y%m%d-%H%M%S")

    if args.dry_run:
        print(f"{len(CASES)} cases × {len(models)} models = "
              f"{len(CASES) * len(models)} renders → {run_dir}")
        for cid, base, kw in CASES:
            print(f"  {cid:16s} base={base.name[:12]}… {kw.get('mat')}/{kw.get('color')}"
                  + (f" env={kw['env']}" if 'env' in kw else "")
                  + (" +bedding" if kw.get('bedding') else ""))
        print("\n── full prompt for case 'mat-chenille' ──")
        print(build_prompt(BED_CHANNEL, mat="chenille", color="greige"))
        return

    if not args.key:
        sys.exit("OPENROUTER_API_KEY missing (env var or --key)")

    run_dir.mkdir(parents=True)
    client = httpx.Client(
        base_url="https://openrouter.ai/api/v1",
        headers={"Authorization": f"Bearer {args.key}",
                 "X-Title": "nano-sofa bakeoff"},
    )
    results = []
    total_cost = 0.0
    for cid, base, kw in CASES:
        prompt = build_prompt(base, **kw)
        for short, slug in models.items():
            t0 = time.time()
            row = {"case": cid, "model": slug, "base": base.name}
            try:
                data = generate(client, slug, prompt, base)
                img = data["data"][0]
                b64 = img["b64_json"]
                ext = (img.get("media_type") or "image/png").split("/")[-1]
                out = run_dir / f"{cid}__{short}.{ext}"
                out.write_bytes(base64.b64decode(b64))
                cost = float((data.get("usage") or {}).get("cost") or 0)
                total_cost += cost
                row.update(file=out.name, cost=cost,
                           seconds=round(time.time() - t0, 1))
                print(f"✓ {cid:16s} {short:9s} {row['seconds']:6.1f}s  ${cost:.4f}")
            except Exception as exc:  # keep going; a dead model ≠ dead run
                row.update(error=str(exc)[:300])
                print(f"✗ {cid:16s} {short:9s} FAILED: {row['error'][:80]}")
            results.append(row)

    (run_dir / "results.json").write_text(json.dumps(
        {"aspect": ASPECT, "total_cost": round(total_cost, 4), "rows": results},
        indent=2))
    write_gallery(run_dir, models, results)
    print(f"\nDone. Total cost ${total_cost:.2f}. Gallery: {run_dir / 'index.html'}")


def write_gallery(run_dir: Path, models: dict, results: list) -> None:
    by = {(r["case"], r["model"]): r for r in results}
    # thumbnails of the base photos for the first column
    for base in {BED_CHANNEL, BED_BUBBLE}:
        (run_dir / f"base__{base.name}").write_bytes(base.read_bytes())
    rows_html = []
    for cid, base, kw in CASES:
        cells = [f'<td class="lbl"><b>{cid}</b><br><small>{kw.get("mat","")}/'
                 f'{kw.get("color","")}</small></td>',
                 f'<td><img src="base__{base.name}" loading="lazy"></td>']
        for short, slug in models.items():
            r = by.get((cid, slug), {})
            if r.get("file"):
                cells.append(f'<td><img src="{r["file"]}" loading="lazy">'
                             f'<small>${r.get("cost", 0):.3f} · {r.get("seconds","?")}s</small></td>')
            else:
                cells.append(f'<td class="err">{(r.get("error") or "—")[:120]}</td>')
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    heads = "".join(f"<th>{s}</th>" for s in models)
    (run_dir / "index.html").write_text(f"""<!DOCTYPE html>
<html lang="pl"><head><meta charset="utf-8"><title>nano-sofa bake-off</title>
<style>
 body{{font:14px/1.4 system-ui;margin:20px;background:#f4f1ea;color:#2b2c28}}
 table{{border-collapse:collapse;width:100%}}
 td,th{{border:1px solid #0002;padding:6px;text-align:center;vertical-align:top}}
 img{{max-width:340px;width:100%;height:auto;border-radius:6px}}
 .lbl{{min-width:110px;text-align:left}} .err{{color:#a33;max-width:200px;font-size:12px}}
 small{{color:#6b6d64;display:block;margin-top:3px}}
</style></head><body>
<h1>Bake-off: baza → modele</h1>
<table><tr><th></th><th>baza</th>{heads}</tr>{''.join(rows_html)}</table>
</body></html>""")


if __name__ == "__main__":
    main()
