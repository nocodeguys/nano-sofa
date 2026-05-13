# Nano Sofa Studio — one-line installer for Windows (PowerShell 5.1+).
#
# Usage (in PowerShell):
#   iwr -useb https://raw.githubusercontent.com/nocodeguys/nano-sofa/main/install.ps1 | iex
#
# What it does:
#   1. Verifies Docker Desktop is installed and running.
#   2. Creates %USERPROFILE%\nano-sofa\ (or $env:NANO_SOFA_DIR if set).
#   3. Downloads the latest docker-compose.yml (with `build:` stripped).
#   4. Pulls images and runs `docker compose up -d`.
#   5. Drops a Launch Nano Sofa.bat in the install folder so future launches
#      are a double-click from File Explorer.
#
# Auto-updates are handled by the Watchtower service in docker-compose.yml,
# which polls GHCR every 5 minutes. No further user action required.

$ErrorActionPreference = 'Stop'

# ─── config ────────────────────────────────────────────────────────────────
$InstallDir = if ($env:NANO_SOFA_DIR) { $env:NANO_SOFA_DIR } else { Join-Path $env:USERPROFILE 'nano-sofa' }
$ComposeUrl = 'https://raw.githubusercontent.com/nocodeguys/nano-sofa/main/docker-compose.yml'
$Port       = 7861
$HealthTimeoutSec = 60

# ─── helpers ───────────────────────────────────────────────────────────────
function Say   ($msg) { Write-Host "▸ $msg" -ForegroundColor Green }
function Warn  ($msg) { Write-Host "! $msg" -ForegroundColor Yellow }
function Fail  ($msg) { Write-Host "✗ $msg" -ForegroundColor Red; exit 1 }

Write-Host ''
Write-Host 'Nano Sofa Studio — installer' -ForegroundColor White
Write-Host "Target folder: $InstallDir" -ForegroundColor DarkGray
Write-Host ''

# ─── 1. preflight: docker ──────────────────────────────────────────────────
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail 'Docker not found. Install Docker Desktop first: https://www.docker.com/products/docker-desktop/'
}

# `docker info` exits 0 only when the daemon is reachable.
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Fail 'Docker is installed but not running. Open Docker Desktop, wait for the whale icon, then re-run this command.'
}

& docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    Fail "'docker compose' is not available. Update Docker Desktop (compose v2 ships built-in)."
}
Say 'Docker is ready.'

# ─── 2. create install dir ─────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $InstallDir            | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir 'outputs') | Out-Null
Set-Location $InstallDir

# ─── 3. fetch docker-compose.yml, strip build: block ───────────────────────
Say 'Downloading docker-compose.yml from main...'
$raw = (Invoke-WebRequest -UseBasicParsing -Uri $ComposeUrl).Content

# Strip the `build:` block (4-space indented, with 6-space children).
# Matches the same shape the Mac installer's awk handles.
$lines = $raw -split "`r?`n"
$out   = New-Object System.Collections.Generic.List[string]
$skip  = $false
foreach ($line in $lines) {
    if (-not $skip) {
        if ($line -match '^    build:\s*$') { $skip = $true; continue }
        $out.Add($line)
    } else {
        if ($line -match '^      ') { continue }                 # child of build:
        if ($line -match '^\s*$')   { $skip = $false; continue } # trailing blank
        $skip = $false
        $out.Add($line)
    }
}
$composePath = Join-Path $InstallDir 'docker-compose.yml'
[System.IO.File]::WriteAllText($composePath, ($out -join "`n"))

# Sanity check; fall back to raw upstream copy if our strip broke YAML.
& docker compose -f $composePath config *> $null
if ($LASTEXITCODE -ne 0) {
    Warn 'Generated docker-compose.yml failed validation — falling back to the raw upstream copy.'
    [System.IO.File]::WriteAllText($composePath, $raw)
}

# ─── 4. pull + start ───────────────────────────────────────────────────────
Say 'Pulling latest images (first run takes 1–3 minutes)...'
& docker compose pull
if ($LASTEXITCODE -ne 0) { Fail 'docker compose pull failed. Check your internet connection and try again.' }

Say 'Starting Nano Sofa...'
& docker compose up -d
if ($LASTEXITCODE -ne 0) { Fail 'docker compose up failed. Run `docker compose logs` in this folder for details.' }

# ─── 5. wait for healthz ───────────────────────────────────────────────────
Say 'Waiting for the server to come up...'
$ready = $false
for ($i = 0; $i -lt $HealthTimeoutSec; $i++) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$Port/healthz" -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}

# ─── 6. drop a double-click launcher ───────────────────────────────────────
$launcher = @'
@echo off
REM Nano Sofa Studio — local launcher (created by install.ps1)
cd /d "%~dp0"
docker info >nul 2>&1
if errorlevel 1 (
    echo Starting Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    echo Waiting for Docker to be ready...
    for /l %%i in (1,1,60) do (
        timeout /t 2 >nul
        docker info >nul 2>&1
        if not errorlevel 1 goto :ready
    )
    echo Docker did not start in time.
    pause
    exit /b 1
)
:ready
docker compose up -d
start "" "http://localhost:7861"
'@
$launcherPath = Join-Path $InstallDir 'Launch Nano Sofa.bat'
[System.IO.File]::WriteAllText($launcherPath, $launcher)

# ─── 7. report ─────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '──────────────────────────────────────────────' -ForegroundColor Green
if ($ready) {
    Write-Host '  Nano Sofa Studio is running.' -ForegroundColor White
    Write-Host "  Open: http://localhost:$Port" -ForegroundColor White
} else {
    Write-Host "  Started, but health check did not pass within ${HealthTimeoutSec}s." -ForegroundColor Yellow
    Write-Host "  Check logs: cd `"$InstallDir`"; docker compose logs -f" -ForegroundColor DarkGray
}
Write-Host ''
Write-Host "  Folder:  $InstallDir"
Write-Host "  Outputs: $InstallDir\outputs"
Write-Host ''
Write-Host '  Auto-updates are on.' -NoNewline -ForegroundColor White
Write-Host ' Watchtower polls GHCR every 5 minutes.'
Write-Host "  Future launches: double-click '$InstallDir\Launch Nano Sofa.bat'" -ForegroundColor DarkGray
Write-Host "  Stop:  cd `"$InstallDir`"; docker compose down"
Write-Host '──────────────────────────────────────────────' -ForegroundColor Green
Write-Host ''
