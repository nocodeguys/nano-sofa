#!/bin/bash
# Nano Sofa Studio v2 — Mac launcher
# Double-click this file in Finder to start the app.
# Requires Docker Desktop to be running.

set -euo pipefail

# Change to the directory that contains this script (and docker-compose.yml).
cd "$(dirname "$0")/.."

echo "Starting Nano Sofa Studio v2..."
echo ""

# Check that Docker is available.
if ! command -v docker &>/dev/null; then
    echo "Docker not found."
    echo "Please install Docker Desktop from https://www.docker.com/products/docker-desktop/"
    echo ""
    echo "Press any key to open the download page..."
    read -n 1
    open "https://www.docker.com/products/docker-desktop/"
    exit 1
fi

# Check that Docker daemon is running.
if ! docker info &>/dev/null 2>&1; then
    echo "Docker is installed but not running."
    echo "Please open Docker Desktop and wait for it to finish starting, then run this script again."
    exit 1
fi

# Pull the latest image so the user always gets the newest version.
echo "Pulling latest image (this may take a minute on first run)..."
docker compose pull || true

# Create the outputs directory if it doesn't exist.
mkdir -p outputs

# Start the app in the foreground so the Terminal window shows logs.
echo ""
echo "Starting server on http://localhost:7861"
echo "Open your browser at: http://localhost:7861"
echo "Press Ctrl+C to stop."
echo ""

docker compose up
