#!/usr/bin/env python3
"""Run the fixed evaluation matrix (scripts/eval_cases.py) against a real
engine and store the renders for scripts/eval_report.py.

The point: the same 12 requests, every time, so two runs (before / after a
prompt change, model A / model B) can be compared by numbers instead of by
scrolling through a gallery.

Usage:
    # Gemini (key from GEMINI_API_KEY or .env)
    .venv/bin/python scripts/eval_matrix.py --model gemini-3.1-flash-image

    # OpenAI direct (key from OPENAI_API_KEY or .env)
    .venv/bin/python scripts/eval_matrix.py --model gpt-image-2.5-flare --quality xhigh

    # Just print what would be sent
    .venv/bin/python scripts/eval_matrix.py --dry-run

    # Subset by substring, custom base photos, named run
    .venv/bin/python scripts/eval_matrix.py --cases catalog --base-sofa path/to/sofa.png --run baseline

Output: outputs/eval/<run>/
    <case>.png          the render (catalog cases are normalized like /api/generate does)
    <case>.prompt.txt   the exact prompt text sent
    manifest.json       per-case parameters, references, cost, timings, expectations

Then:  .venv/bin/python scripts/eval_report.py report outputs/eval/<run>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from dataclasses import replace as dataclass_replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "app-v2"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import eval_cases  # noqa: E402

DEFAULT_BED = REPO_ROOT / "outputs/v2-uploads/02841ec18b384dda92fbf8db36e5f286.png"
EVAL_ROOT = REPO_ROOT / "outputs" / "eval"

# What a correct render should measure, per shot type. Used by eval_report to
# mark ✓/✗; they come from the catalog framing contract (78–84 % of the frame
# width for a hero) and from what "close-up" / "macro" mean.
EXPECTATIONS = {
    "hero":          {"product_width_share": [0.78, 0.84]},
    "close_up":      {"mask_share": [0.60, 1.00]},
    "detail_fabric": {"mask_share": [0.90, 1.00]},
    "":              {"product_width_share": [0.78, 0.84]},   # ui_default == hero
}


def _dotenv() -> dict[str, str]:
    """Minimal .env reader — no dependency, no export, values stay in-process."""
    out: dict[str, str] = {}
    path = REPO_ROOT / ".env"
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _key(name: str) -> str:
    return os.environ.get(name) or _dotenv().get(name, "")


def _select_cases(args) -> list[eval_cases.Case]:
    from studio.openai_images import OPENAI_MODELS
    engine = "openai" if args.model in OPENAI_MODELS else "gemini"
    cases = [c for c in eval_cases.CASES if c.engine == engine]
    if not args.include_ui_default:
        cases = [c for c in cases if "ui_default" not in c.id]
    if not args.editorial:
        cases = [c for c in cases if not c.freeform]
    if args.cases:
        cases = [c for c in cases if any(s in c.id for s in args.cases)]
    return cases


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=eval_cases.GEMINI_MODEL)
    ap.add_argument("--quality", default="", help="OpenAI quality tier (low…max); ignored for Gemini")
    ap.add_argument("--cases", nargs="*", default=[], help="substring filters on case ids")
    ap.add_argument("--base-bed", type=Path, default=DEFAULT_BED)
    ap.add_argument("--base-sofa", type=Path, default=None, help="sofa base photo (sofa cases skipped without it)")
    ap.add_argument("--run", default="", help="run name (default: <timestamp>-<model>)")
    ap.add_argument("--dry-run", action="store_true", help="build prompts and plans, call nothing")
    ap.add_argument("--editorial", action="store_true", help="include the editorial case")
    ap.add_argument("--include-ui-default", action="store_true")
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between calls")
    args = ap.parse_args()

    from app.core.generator import generate
    from studio.normalize import PROFILES, normalize_packshot
    from studio.openai_images import OPENAI_MODELS, generate_product_openai

    engine = "openai" if args.model in OPENAI_MODELS else "gemini"
    cases = _select_cases(args)
    if not cases:
        print("no cases selected", file=sys.stderr)
        return 2

    bases = {"bed": args.base_bed, "sofa": args.base_sofa}
    for kind, path in bases.items():
        if path is not None and not path.exists():
            print(f"base image for {kind} not found: {path}", file=sys.stderr)
            return 2

    key = ""
    if not args.dry_run:
        key = _key("OPENAI_API_KEY" if engine == "openai" else "GEMINI_API_KEY")
        if not key:
            print(f"missing {'OPENAI_API_KEY' if engine == 'openai' else 'GEMINI_API_KEY'} "
                  f"(env or .env) — use --dry-run to inspect without calling", file=sys.stderr)
            return 2

    run = args.run or f"{time.strftime('%Y%m%d-%H%M%S')}-{args.model.replace('/', '_')}"
    out_dir = EVAL_ROOT / run
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "run": run, "model": args.model, "engine": engine, "quality": args.quality,
        "created_at": time.time(), "git_sha": _git_sha(), "cases": [],
    }
    total_cost = 0.0
    for case in cases:
        base = None if case.freeform else bases.get(case.kind)
        if not case.freeform and base is None:
            print(f"skip {case.id}: no base photo for {case.kind} (pass --base-{case.kind})")
            continue

        req = eval_cases.build_request(case, base)
        req = dataclass_replace(req, model_id=args.model, api_key=key or req.api_key)
        rendered = eval_cases.render(dataclass_replace(case, engine=engine), req, base)
        stats = eval_cases.prompt_stats(rendered.prompt)
        entry = {
            "id": case.id, "kind": case.kind, "mode": case.mode, "shot": case.shot,
            "shot_type": req.shot_type, "model": args.model,
            "upholstery_hex": req.upholstery_hex, "material_id": req.material_id,
            "color_id": req.color_id,
            "backdrop_hex": _rgb_hex(PROFILES["ivory"].background) if case.mode == "catalog" else "",
            "references": [role for role, _label in rendered.references],
            "n_refs": len(rendered.references),
            "prompt_sha256": hashlib.sha256(rendered.prompt.encode()).hexdigest(),
            "prompt_stats": stats,
            "expect": EXPECTATIONS.get(case.shot, {}),
            "file": "", "cost": 0.0, "elapsed_ms": 0, "error": "",
        }
        print(f"{case.id:<36} refs={entry['n_refs']:<2} chars={stats['chars']:<6} "
              f"camera@{stats['camera_offset_pct']}%")
        if args.dry_run:
            for i, (role, label) in enumerate(rendered.references, 1):
                print(f"    {i}. {role:<22} {label}")
            manifest["cases"].append(entry)
            continue

        (out_dir / f"{case.id}.prompt.txt").write_text(rendered.prompt, encoding="utf-8")
        t0 = time.monotonic()
        try:
            if engine == "openai":
                result = generate_product_openai(
                    dataclass_replace(req, engine_quality=args.quality), key
                )
            else:
                result = generate(req)
        except Exception as exc:  # noqa: BLE001 — record and move on
            entry["error"] = f"{type(exc).__name__}: {exc}"
            manifest["cases"].append(entry)
            print(f"    ERROR {entry['error']}")
            continue
        entry["elapsed_ms"] = result.elapsed_ms or int((time.monotonic() - t0) * 1000)
        entry["cost"] = float(result.actual_cost or 0.0)
        total_cost += entry["cost"]
        if not result.success or result.output_path is None:
            entry["error"] = f"{result.error_code}: {result.error_detail or result.error_message}"
            print(f"    FAILED {entry['error']}")
        else:
            src = Path(result.output_path)
            if case.mode == "catalog":
                try:
                    normalize_packshot(src, "ivory")
                except Exception as exc:  # noqa: BLE001
                    entry["error"] = f"normalize: {exc}"
            dst = out_dir / f"{case.id}{src.suffix.lower() or '.png'}"
            shutil.copy2(src, dst)
            entry["file"] = dst.name
            print(f"    ok  {dst.name}  ${entry['cost']:.4f}  {entry['elapsed_ms']} ms")
        manifest["cases"].append(entry)
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        time.sleep(args.sleep)

    if args.dry_run:
        print(f"\ndry run: {len(manifest['cases'])} cases, nothing sent")
        return 0
    manifest["total_cost"] = round(total_cost, 4)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nrun saved: {out_dir}  total ${total_cost:.4f}")
    print(f"next: .venv/bin/python scripts/eval_report.py report {out_dir}")
    return 0


def _rgb_hex(rgb) -> str:
    r, g, b = rgb
    return f"#{r:02X}{g:02X}{b:02X}"


def _git_sha() -> str:
    try:
        import subprocess
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


if __name__ == "__main__":
    sys.exit(main())
