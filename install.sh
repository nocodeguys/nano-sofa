#!/usr/bin/env bash
# Nano Sofa Studio — one-line installer for macOS and Linux.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/nocodeguys/nano-sofa/main/install.sh | bash
#
# What it does:
#   1. Verifies Docker Desktop is installed and running.
#   2. Creates ~/nano-sofa/ (or $NANO_SOFA_DIR if you set it).
#   3. Downloads the latest docker-compose.yml (with `build:` stripped).
#   4. Pulls images and runs `docker compose up -d`.
#   5. Drops a locally-created launch.command that bypasses macOS Gatekeeper
#      (only browser-downloaded files get quarantined — locally-written files
#      do not), so future launches can be a double-click from Finder.
#
# Auto-updates are handled by the Watchtower service in docker-compose.yml,
# which polls GHCR every 5 minutes. No further user action required.

set -euo pipefail

# ─── config ────────────────────────────────────────────────────────────────
INSTALL_DIR="${NANO_SOFA_DIR:-$HOME/nano-sofa}"
COMPOSE_URL="https://raw.githubusercontent.com/nocodeguys/nano-sofa/main/docker-compose.yml"
PORT=7861
HEALTH_TIMEOUT=60   # seconds

# ─── pretty output ─────────────────────────────────────────────────────────
if [ -t 1 ]; then
    BOLD=$'\033[1m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'
    RED=$'\033[1;31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
    BOLD=""; GREEN=""; YELLOW=""; RED=""; DIM=""; RESET=""
fi
say()  { printf "%s▸%s %s\n" "${GREEN}" "${RESET}" "$*"; }
warn() { printf "%s!%s %s\n" "${YELLOW}" "${RESET}" "$*" >&2; }
die()  { printf "%s✗%s %s\n" "${RED}" "${RESET}" "$*" >&2; exit 1; }

printf "%s\n" "${BOLD}Nano Sofa Studio — installer${RESET}"
printf "%sTarget folder: %s%s\n\n" "${DIM}" "${INSTALL_DIR}" "${RESET}"

# ─── 1. preflight: docker ──────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
    die "Docker not found. Install Docker Desktop first: https://www.docker.com/products/docker-desktop/"
fi
if ! docker info >/dev/null 2>&1; then
    die "Docker is installed but not running. Open Docker Desktop, wait for the whale icon, then re-run."
fi
if ! docker compose version >/dev/null 2>&1; then
    die "'docker compose' is not available. Update Docker Desktop (compose v2 ships built-in)."
fi
say "Docker is ready."

# ─── 2. create install dir ─────────────────────────────────────────────────
mkdir -p "${INSTALL_DIR}/outputs"
cd "${INSTALL_DIR}"

# ─── 3. fetch docker-compose.yml, strip build: block ───────────────────────
# Stripping `build:` keeps `docker compose` from trying to build locally on
# machines that don't have the source — they should always pull the prebuilt
# image from GHCR.
say "Downloading docker-compose.yml from main..."
TMP=$(mktemp)
trap 'rm -f "${TMP}"' EXIT
curl -fsSL "${COMPOSE_URL}" -o "${TMP}"

awk '
    /^    build:[[:space:]]*$/ { skip = 1; next }
    skip && /^      / { next }
    skip && /^[[:space:]]*$/ { skip = 0; next }
    { skip = 0; print }
' "${TMP}" > docker-compose.yml

# Sanity-check that the result still parses.
if ! docker compose -f docker-compose.yml config >/dev/null 2>&1; then
    warn "Generated docker-compose.yml failed validation — falling back to the raw upstream copy."
    cp "${TMP}" docker-compose.yml
fi

# ─── 4. pull + start ───────────────────────────────────────────────────────
say "Pulling latest images (first run takes 1–3 minutes)..."
docker compose pull

say "Starting Nano Sofa..."
docker compose up -d

# ─── 5. wait for healthz ───────────────────────────────────────────────────
say "Waiting for the server to come up..."
for _ in $(seq 1 ${HEALTH_TIMEOUT}); do
    if curl -fsS "http://localhost:${PORT}/healthz" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 1
done

# ─── 6. drop a locally-created launcher (no quarantine xattr) ──────────────
# Because this file is written by bash on the local machine — not downloaded
# through a browser — macOS does not flag it with com.apple.quarantine and
# Gatekeeper stays out of the way. Users can double-click it from Finder, or
# drag it to the Dock.
cat > "${INSTALL_DIR}/launch.command" <<'LAUNCHER'
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
LAUNCHER
chmod +x "${INSTALL_DIR}/launch.command"

# ─── 7. report ─────────────────────────────────────────────────────────────
printf "\n%s──────────────────────────────────────────────%s\n" "${GREEN}" "${RESET}"
if [ "${ready:-0}" = "1" ]; then
    printf "  %sNano Sofa Studio is running.%s\n" "${BOLD}" "${RESET}"
    printf "  Open: %shttp://localhost:%s%s\n" "${BOLD}" "${PORT}" "${RESET}"
else
    printf "  %sStarted, but health check did not pass within %ss.%s\n" "${YELLOW}" "${HEALTH_TIMEOUT}" "${RESET}"
    printf "  Check logs: %scd \"%s\" && docker compose logs -f%s\n" "${DIM}" "${INSTALL_DIR}" "${RESET}"
fi
printf "\n"
printf "  Folder:  %s\n" "${INSTALL_DIR}"
printf "  Outputs: %s/outputs\n" "${INSTALL_DIR}"
printf "\n"
printf "  %sAuto-updates are on.%s Watchtower polls GHCR every 5 minutes.\n" "${BOLD}" "${RESET}"
printf "  Future launches: double-click %s%s/launch.command%s\n" "${DIM}" "${INSTALL_DIR}" "${RESET}"
printf "  Stop:  cd \"%s\" && docker compose down\n" "${INSTALL_DIR}"
printf "%s──────────────────────────────────────────────%s\n\n" "${GREEN}" "${RESET}"
