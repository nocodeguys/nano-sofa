@echo off
REM Nano Sofa Studio v2 — Windows launcher
REM Double-click this file to start the app.
REM Requires Docker Desktop to be running.

setlocal enabledelayedexpansion

REM Change to the directory that contains docker-compose.yml (one level up from install/).
cd /d "%~dp0.."

echo Starting Nano Sofa Studio v2...
echo.

REM Check that Docker is available.
where docker >nul 2>&1
if errorlevel 1 (
    echo Docker not found.
    echo Please install Docker Desktop from https://www.docker.com/products/docker-desktop/
    echo.
    echo Press any key to open the download page...
    pause >nul
    start https://www.docker.com/products/docker-desktop/
    exit /b 1
)

REM Check that Docker daemon is running.
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker is installed but not running.
    echo Please open Docker Desktop and wait for it to finish starting, then run this script again.
    echo.
    pause
    exit /b 1
)

REM Pull the latest image.
echo Pulling latest image (this may take a minute on first run)...
docker compose pull

REM Create the outputs directory if it doesn't exist.
if not exist outputs mkdir outputs

REM Start the app.
echo.
echo Starting server on http://localhost:7861
echo Open your browser at: http://localhost:7861
echo Press Ctrl+C to stop.
echo.

docker compose up
