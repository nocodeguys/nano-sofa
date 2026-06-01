#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! docker info >/dev/null 2>&1; then
    osascript -e 'tell application "Docker Desktop" to activate' 2>/dev/null || true
    echo "Waiting for Docker Desktop to start..."
    for _ in $(seq 1 60); do
        docker info >/dev/null 2>&1 && break
        sleep 2
    done
fi
docker compose up -d
open "http://localhost:7861"
