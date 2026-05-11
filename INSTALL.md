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

## Quick start (two ways to launch)

### Path A — One command, no files to download

Open a Terminal (Mac) or Command Prompt (Windows) and run:

```
docker run --rm -p 7861:7861 -v "$PWD/outputs:/app/outputs" ghcr.io/nocodeguys/nano-sofa:latest
```

On Windows Command Prompt, replace `"$PWD/outputs"` with the full path to a
folder where you want generated images saved, for example:

```
docker run --rm -p 7861:7861 -v "C:\Users\YourName\nano-sofa-outputs:/app/outputs" ghcr.io/nocodeguys/nano-sofa:latest
```

Once you see `Nano Sofa v2 starting on http://0.0.0.0:7861`, open your browser
at http://localhost:7861.

---

### Path B — Double-click launcher (recommended for non-technical users)

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

### Port 7861 is already in use

**Symptom:** The browser shows "This site can't be reached" and the Terminal
shows an error like `bind: address already in use` or `port is already
allocated`.

**Fix (Path A — docker run):** Use a different host port. Replace `7861:7861`
with `7862:7861` (or any free port):

```
docker run --rm -p 7862:7861 -v "$PWD/outputs:/app/outputs" ghcr.io/nocodeguys/nano-sofa:latest
```

Then open http://localhost:7862 instead.

**Fix (Path B — docker compose):** Open `docker-compose.yml` in a text editor
and change `"7861:7861"` to `"7862:7861"`, then run the launcher again. Open
http://localhost:7862 in your browser.

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
