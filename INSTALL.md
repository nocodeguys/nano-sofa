# Nano Sofa Studio v2 — Installation Guide

Nano Sofa Studio runs entirely inside Docker. You do not need Python, Node.js,
or any other runtime on your machine. You only need Docker Desktop.

---

## Prerequisites

Install Docker Desktop for your operating system:

- Mac: https://www.docker.com/products/docker-desktop/
- Windows: https://www.docker.com/products/docker-desktop/

After installing, open Docker Desktop and wait for the whale icon in the menu
bar (Mac) or taskbar (Windows) to show "Docker Desktop is running".

---

## Quick start

### Path A — One-line install (recommended)

The simplest way. Open a Terminal (Mac/Linux) or PowerShell (Windows) and paste
the matching line. This downloads the latest config into `~/nano-sofa/`,
pulls the image, and starts the app — no zip downloads, no Gatekeeper
"unidentified developer" dialog, no manual file extraction.

**Mac / Linux** — open Terminal and paste:

```
curl -fsSL https://raw.githubusercontent.com/nocodeguys/nano-sofa/main/install.sh | bash
```

**Windows** — open PowerShell and paste:

```
iwr -useb https://raw.githubusercontent.com/nocodeguys/nano-sofa/main/install.ps1 | iex
```

When the installer finishes you will see a green box with the localhost URL —
open http://localhost:7861 in your browser.

Subsequent launches: double-click the `launch.command` (Mac) or
`Launch Nano Sofa.bat` (Windows) file the installer placed inside the
nano-sofa folder. These files are created locally on your machine, so macOS
does **not** quarantine them and Gatekeeper stays out of the way.

You do not need to re-run the installer for updates — the included Watchtower
service pulls new versions every ~5 minutes silently. See "Automatic updates"
below.

---

### Path B — Bundled zip (offline / air-gapped installs)

If you cannot run a one-liner (offline machine, locked-down corporate laptop),
grab the latest `nano-sofa-vX.Y.Z.zip` from the
[Releases page](https://github.com/nocodeguys/nano-sofa/releases) and follow
"Path D" below for the double-click launcher.

---

### Path C — One command, no files to download

Open a Terminal (Mac/Linux) and run:

```
mkdir -p outputs && docker run --rm -p 7861:7861 -v "$PWD/outputs:/app/outputs" ghcr.io/nocodeguys/nano-sofa:latest
```

The `mkdir -p outputs` part matters — it creates the host folder *as you*
before Docker mounts it, so the container can write generated images into it.
If you skip it, Docker will create the folder as root and the app will fail
with "Permission denied" when saving renders.

On Windows Command Prompt, first create a folder for outputs, then mount it
with its full path:

```
mkdir C:\Users\YourName\nano-sofa-outputs
docker run --rm -p 7861:7861 -v "C:\Users\YourName\nano-sofa-outputs:/app/outputs" ghcr.io/nocodeguys/nano-sofa:latest
```

Once you see `Nano Sofa v2 starting on http://0.0.0.0:7861`, open your browser
at http://localhost:7861.

---

### Path D — Double-click launcher (from the bundled zip)

1. Download the `nano-sofa` folder you received and place it anywhere on your
   computer (Desktop is fine).

2. Inside the folder you will see an `install/` sub-folder.

   - **Mac**: double-click `install/start-mac.command`.
     If macOS asks "Are you sure?", click Open.

   - **Windows**: double-click `install/start-windows.bat`.
     If Windows Defender SmartScreen appears, click "More info" then
     "Run anyway".

3. A Terminal or Command Prompt window opens. The first run downloads the
   Docker image (~400 MB) — this takes 1-3 minutes depending on your internet
   connection. Subsequent starts are instant.

4. When you see the line:

   ```
   Nano Sofa v2 starting on http://0.0.0.0:7861
   ```

   open your browser and go to http://localhost:7861.

5. To stop the app, click back into the Terminal/Command Prompt window and
   press **Ctrl + C**.

---

## Automatic updates

Once the app is running, you do **not** need to pull new versions manually.
A small companion container called Watchtower runs in the background and
checks GitHub every 5 minutes for a newer build. When one is published it
silently pulls it, restarts Nano Sofa with the new version, and cleans up the
old image. No action from you.

Practically this means:

- Leave the launcher window open (or keep Docker Desktop running) and the app
  stays current on its own.
- A live generation will not be interrupted mid-flight — Watchtower waits for
  the next idle moment before restarting the container.
- Watchtower only touches the `nano-sofa` container. Any other Docker apps you
  run are ignored.

If you ever want to force an update right now instead of waiting for the next
5-minute poll, just close the launcher window and double-click it again — the
launcher pulls the latest image before starting.

---

## Getting your Gemini API key

Nano Sofa Studio does not store API keys. You paste your own key directly in
the browser UI each session. The key stays in your browser only — it is never
sent anywhere except directly to Google's Gemini API.

1. Go to https://aistudio.google.com/app/apikey
2. Sign in with your Google account.
3. Click "Create API key".
4. Copy the key (starts with `AIza...`).
5. Paste it into the "API Key" field at the top of the Nano Sofa Studio page.

---

## Troubleshooting

### Docker not installed or not running

**Symptom:** The launcher script shows "Docker not found" or "Docker is
installed but not running."

**Fix:**

1. If Docker is not installed, download it from
   https://www.docker.com/products/docker-desktop/ and follow the installer.

2. If Docker is installed but not running, open the Docker Desktop application
   from your Applications folder (Mac) or Start Menu (Windows) and wait until
   the status shows "Running" (the whale icon stops animating).

3. Run the launcher again.

---

### Permission denied when saving generated images

**Symptom:** The browser shows a generation error, and the Terminal log contains
something like `PermissionError: [Errno 13] Permission denied: '/app/outputs/...'`
or `cannot create directory '/app/outputs/...': Permission denied`.

**Cause:** The host `outputs/` folder was created by Docker itself (running as
root) instead of by you, so the in-container user (`sofa`, UID 1001) can't
write into it through the bind mount.

**Fix:**

1. Stop the container (Ctrl+C in the Terminal).

2. Re-create the folder as your own user, then re-launch:

   - Mac / Linux:
     ```
     rm -rf outputs
     mkdir -p outputs
     ```
   - Windows (PowerShell):
     ```
     Remove-Item -Recurse -Force outputs
     New-Item -ItemType Directory outputs
     ```

3. If you used the one-line `docker run` command, re-run it — the updated
   command in this guide now prefixes `mkdir -p outputs &&` so this won't
   happen again.

4. If you used the launcher script, just double-click it again — the script
   creates the folder for you.

---

### Port 7861 is already in use

**Symptom:** The browser shows "This site can't be reached" and the Terminal
shows an error like `bind: address already in use` or `port is already
allocated`.

**Fix (Path C — docker run):** Use a different host port. Replace `7861:7861`
with `7862:7861` (or any free port):

```
docker run --rm -p 7862:7861 -v "$PWD/outputs:/app/outputs" ghcr.io/nocodeguys/nano-sofa:latest
```

Then open http://localhost:7862 instead.

**Fix (Paths A / B / D — docker compose):** Open `~/nano-sofa/docker-compose.yml`
(or `docker-compose.yml` inside the bundle folder) in a text editor and change
`"7861:7861"` to `"7862:7861"`, then re-launch. Open http://localhost:7862 in
your browser.

To find out what is using port 7861:

- Mac/Linux: `lsof -i :7861`
- Windows: `netstat -ano | findstr :7861`

---

### API key rejected or generation fails

**Symptom:** After clicking Generate, the app shows an error like "Brak klucza
API" (Missing API key) or the generation fails immediately.

**Fix:**

1. Make sure you copied the full key — it starts with `AIza` and is
   approximately 39 characters long. There should be no leading or trailing
   spaces.

2. Check that the key has not been revoked. Visit
   https://aistudio.google.com/app/apikey and confirm the key is listed and
   active.

3. If you recently created the key, wait 30 seconds and try again — new keys
   can take a moment to activate.

4. If the key is valid but generations still fail with a server error, the
   Gemini API may be temporarily busy. The app retries automatically up to
   4 times with exponential backoff. Wait a minute and try again.

---

## Where generated images are saved

All generated images are written to the `outputs/` folder inside the
nano-sofa directory on your computer. This folder is mounted into the
container as a Docker volume, so images persist even after you stop and
restart the container.

You can open `outputs/` in Finder (Mac) or File Explorer (Windows) at any
time to copy or back up your renders.
