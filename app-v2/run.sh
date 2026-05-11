#!/usr/bin/env bash
# Run Nano Sofa Studio v2 (FastAPI + React prototype).
# From the repo root or anywhere — paths are resolved relative to this file.

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

# Use the project venv if present, else system python3.
if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PY="$REPO_ROOT/.venv/bin/python"
else
  PY="$(command -v python3)"
fi

# Install v2 deps into whichever interpreter we're using.
"$PY" -m pip install -q -r "$HERE/requirements.txt"

cd "$REPO_ROOT"
exec "$PY" "$HERE/server.py"
