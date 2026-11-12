"""Diagnose OpenRouter 402 "Insufficient credits" on a key that has funds.

Reads OPENROUTER_API_KEY from the environment (or the repo's .env) and prints
the key's own limit / remaining budget plus the account credits, then — with
--probe MODEL — sends one cheap 1:1 text-only image request and prints the
raw 402 body (limit_source / reason) if it fails.

    .venv/bin/python scripts/openrouter_diag.py
    .venv/bin/python scripts/openrouter_diag.py --probe openai/gpt-image-1-mini
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx

API = "https://openrouter.ai/api/v1"


def _key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    env = Path(__file__).resolve().parent.parent / ".env"
    if not key and env.is_file():
        for line in env.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("Set OPENROUTER_API_KEY (env or .env).")
    return key


def _show(label: str, r: httpx.Response) -> None:
    print(f"\n== {label}: HTTP {r.status_code}")
    try:
        print(json.dumps(r.json(), indent=2)[:3000])
    except ValueError:
        print(r.text[:3000])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", default="", help="model slug for one minimal image request")
    args = ap.parse_args()
    headers = {"Authorization": f"Bearer {_key()}"}
    with httpx.Client(timeout=300, headers=headers) as c:
        _show("GET /key", c.get(f"{API}/key"))
        _show("GET /credits", c.get(f"{API}/credits"))
        if args.probe:
            payload = {"model": args.probe, "prompt": "a plain wooden cube on white", "aspect_ratio": "1:1"}
            if "gpt-image" in args.probe:
                payload["quality"] = "low"
            r = c.post(f"{API}/images", json=payload)
            if r.status_code < 400:
                usage = r.json().get("usage")
                print(f"\n== POST /images {args.probe}: OK usage={usage}")
            else:
                _show(f"POST /images {args.probe}", r)


if __name__ == "__main__":
    main()
