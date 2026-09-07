"""Push the runtime catalogue (catalog.json + material references) to GitHub.

The published app runs from a Docker image that CI builds on every push to
``main``. A catalogue edit made in the Katalog panel is promoted locally first
(the saving instance is correct immediately) and then committed here through
the GitHub Git Data API so the files live in the repository, the image gets
rebuilt with them, and every other instance receives the same catalogue via
Watchtower.

Why the Git Data API and not the Contents API: Contents is one file per
commit and rejects the second file with a SHA conflict; Git Data lets us put
catalog.json and N images into ONE commit and refuses a non-fast-forward ref
update, which is exactly the optimistic concurrency we want.

Configuration (environment, never baked into the image):
  CATALOG_GIT_TOKEN    fine-grained PAT, Contents: read/write on ONE repo
  CATALOG_GIT_REPO     owner/name              (default nocodeguys/nano-sofa)
  CATALOG_GIT_BRANCH   branch to commit to     (default main)
  CATALOG_GIT_AUTHOR   "Name <email>" for the commit author (optional)

Only two paths are ever written: ``app-v2/catalog.json`` and files directly
under ``app-v2/material-references/``. Nothing else in the repository can be
touched through this module, whatever the admin payload contains.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from studio.paths import logger

_API = "https://api.github.com"
_TIMEOUT_S = float(os.environ.get("CATALOG_GIT_TIMEOUT_S", "60"))
_CATALOG_REPO_PATH = "app-v2/catalog.json"
_REFERENCES_REPO_DIR = "app-v2/material-references"
_ALLOWED_REFERENCE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


class CatalogGitError(RuntimeError):
    """A push failed. `retryable` says whether trying again later makes sense
    (network / 5xx / ref moved) as opposed to a configuration problem."""

    def __init__(self, message: str, *, retryable: bool = True, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.detail = detail


@dataclass(frozen=True)
class GitConfig:
    token: str
    repo: str
    branch: str
    author_name: str = ""
    author_email: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.repo and self.branch)

    def public(self) -> dict:
        """What the admin UI may see — never the token."""
        return {
            "enabled": self.enabled,
            "repo": self.repo,
            "branch": self.branch,
            "url": f"https://github.com/{self.repo}" if self.repo else None,
        }


def load_config() -> GitConfig:
    author = os.environ.get("CATALOG_GIT_AUTHOR", "").strip()
    name, email = "", ""
    if author:
        if "<" in author and author.endswith(">"):
            name, _, email = author.rpartition("<")
            name, email = name.strip(), email.rstrip(">").strip()
        else:
            name = author
    return GitConfig(
        token=os.environ.get("CATALOG_GIT_TOKEN", "").strip(),
        repo=os.environ.get("CATALOG_GIT_REPO", "nocodeguys/nano-sofa").strip().strip("/"),
        branch=os.environ.get("CATALOG_GIT_BRANCH", "main").strip(),
        author_name=name,
        author_email=email,
    )


def git_blob_sha(data: bytes) -> str:
    """SHA-1 git would assign to `data` as a blob — lets us skip re-uploading
    files that are already identical in the repository."""
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _client(cfg: GitConfig) -> httpx.Client:
    return httpx.Client(
        base_url=_API,
        timeout=_TIMEOUT_S,
        headers={
            "Authorization": f"Bearer {cfg.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nano-sofa-catalog-admin",
        },
    )


def _raise_for(resp: httpx.Response, what: str) -> None:
    if resp.status_code < 400:
        return
    body = resp.text[:300]
    if resp.status_code in (401, 403):
        raise CatalogGitError(
            "Token GitHub jest nieprawidłowy albo nie ma prawa zapisu do repozytorium.",
            retryable=False, detail=f"{what}: {resp.status_code} {body}",
        )
    if resp.status_code == 404:
        raise CatalogGitError(
            "Repozytorium lub gałąź nie istnieje albo token jej nie widzi.",
            retryable=False, detail=f"{what}: 404 {body}",
        )
    if resp.status_code == 422 and what == "update-ref":
        raise CatalogGitError(
            "Gałąź zmieniła się w międzyczasie — zapis zostanie ponowiony.",
            retryable=True, detail=f"{what}: 422 {body}",
        )
    raise CatalogGitError(
        f"GitHub odpowiedział błędem ({resp.status_code}).",
        retryable=resp.status_code >= 500 or resp.status_code == 429,
        detail=f"{what}: {resp.status_code} {body}",
    )


def _list_remote_references(client: httpx.Client, cfg: GitConfig, ref_sha: str) -> dict[str, str]:
    """name → blob sha of files currently under material-references on the
    branch. Empty when the directory does not exist yet."""
    resp = client.get(
        f"/repos/{cfg.repo}/contents/{_REFERENCES_REPO_DIR}", params={"ref": ref_sha}
    )
    if resp.status_code == 404:
        return {}
    _raise_for(resp, "list-references")
    return {
        item["name"]: item["sha"]
        for item in resp.json()
        if item.get("type") == "file"
    }


def _create_blob(client: httpx.Client, cfg: GitConfig, data: bytes) -> str:
    resp = client.post(
        f"/repos/{cfg.repo}/git/blobs",
        json={"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"},
    )
    _raise_for(resp, "create-blob")
    return resp.json()["sha"]


def push_catalog(
    *,
    catalog_bytes: bytes,
    references_dir: Path,
    message: str,
    cfg: Optional[GitConfig] = None,
    max_attempts: int = 3,
) -> dict:
    """Commit catalog.json + the whole material-references directory to the
    configured branch. Files identical to the repository are not re-uploaded;
    repository files missing locally are deleted (the local directory is the
    complete desired state). Returns {sha, url, files_changed, attempts}."""
    cfg = cfg or load_config()
    if not cfg.enabled:
        raise CatalogGitError(
            "Zapis do repozytorium nie jest skonfigurowany (brak CATALOG_GIT_TOKEN).",
            retryable=False,
        )

    local: dict[str, bytes] = {}
    if references_dir.is_dir():
        for path in sorted(references_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in _ALLOWED_REFERENCE_EXTENSIONS:
                local[path.name] = path.read_bytes()

    last_error: Optional[CatalogGitError] = None
    with _client(cfg) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                ref = client.get(f"/repos/{cfg.repo}/git/ref/heads/{cfg.branch}")
                _raise_for(ref, "get-ref")
                base_commit = ref.json()["object"]["sha"]
                commit = client.get(f"/repos/{cfg.repo}/git/commits/{base_commit}")
                _raise_for(commit, "get-commit")
                base_tree = commit.json()["tree"]["sha"]

                remote_refs = _list_remote_references(client, cfg, base_commit)
                catalog_entry = client.get(
                    f"/repos/{cfg.repo}/contents/{_CATALOG_REPO_PATH}",
                    params={"ref": base_commit},
                )
                remote_catalog_sha = (
                    catalog_entry.json().get("sha") if catalog_entry.status_code == 200 else None
                )

                tree: list[dict] = []
                changed: list[str] = []
                if remote_catalog_sha != git_blob_sha(catalog_bytes):
                    tree.append({
                        "path": _CATALOG_REPO_PATH, "mode": "100644", "type": "blob",
                        "sha": _create_blob(client, cfg, catalog_bytes),
                    })
                    changed.append(_CATALOG_REPO_PATH)
                for name, data in local.items():
                    if remote_refs.get(name) == git_blob_sha(data):
                        continue
                    tree.append({
                        "path": f"{_REFERENCES_REPO_DIR}/{name}", "mode": "100644",
                        "type": "blob", "sha": _create_blob(client, cfg, data),
                    })
                    changed.append(f"{_REFERENCES_REPO_DIR}/{name}")
                for name in remote_refs:
                    if name not in local and Path(name).suffix.lower() in _ALLOWED_REFERENCE_EXTENSIONS:
                        tree.append({
                            "path": f"{_REFERENCES_REPO_DIR}/{name}", "mode": "100644",
                            "type": "blob", "sha": None,
                        })
                        changed.append(f"-{_REFERENCES_REPO_DIR}/{name}")

                if not tree:
                    logger.info("catalog git: nothing to commit (repo already up to date)")
                    return {
                        "sha": base_commit,
                        "url": f"https://github.com/{cfg.repo}/commit/{base_commit}",
                        "files_changed": [],
                        "attempts": attempt,
                        "noop": True,
                    }

                new_tree = client.post(
                    f"/repos/{cfg.repo}/git/trees", json={"base_tree": base_tree, "tree": tree}
                )
                _raise_for(new_tree, "create-tree")
                commit_payload: dict = {
                    "message": message,
                    "tree": new_tree.json()["sha"],
                    "parents": [base_commit],
                }
                if cfg.author_name:
                    commit_payload["author"] = {
                        "name": cfg.author_name,
                        "email": cfg.author_email or "catalog@nano-sofa.local",
                        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                new_commit = client.post(f"/repos/{cfg.repo}/git/commits", json=commit_payload)
                _raise_for(new_commit, "create-commit")
                sha = new_commit.json()["sha"]
                updated = client.patch(
                    f"/repos/{cfg.repo}/git/refs/heads/{cfg.branch}",
                    json={"sha": sha, "force": False},
                )
                _raise_for(updated, "update-ref")
                logger.info("catalog git: committed %s (%d files)", sha[:10], len(changed))
                return {
                    "sha": sha,
                    "url": f"https://github.com/{cfg.repo}/commit/{sha}",
                    "files_changed": changed,
                    "attempts": attempt,
                    "noop": False,
                }
            except CatalogGitError as exc:
                last_error = exc
                if not exc.retryable or attempt == max_attempts:
                    raise
                logger.warning("catalog git: attempt %d failed (%s), retrying", attempt, exc.detail)
                time.sleep(1.5 * attempt)
            except httpx.HTTPError as exc:
                last_error = CatalogGitError(
                    "Błąd sieci przy zapisie do GitHub.", retryable=True, detail=str(exc)[:300]
                )
                if attempt == max_attempts:
                    raise last_error from exc
                time.sleep(1.5 * attempt)
    raise last_error or CatalogGitError("Zapis do GitHub nie powiódł się.")


def workflow_status(sha: str, cfg: Optional[GitConfig] = None) -> dict:
    """State of the CI run(s) for a commit: the admin UI turns this into
    "buduje / gotowe / testy padły". Public repos need no token for this, but
    we send it when present to avoid the anonymous rate limit."""
    cfg = cfg or load_config()
    if not cfg.repo:
        return {"state": "unknown", "runs": []}
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "nano-sofa-catalog-admin",
    }
    if cfg.token:
        headers["Authorization"] = f"Bearer {cfg.token}"
    try:
        resp = httpx.get(
            f"{_API}/repos/{cfg.repo}/actions/runs",
            params={"head_sha": sha, "per_page": 10},
            headers=headers, timeout=20,
        )
    except httpx.HTTPError as exc:
        return {"state": "unknown", "runs": [], "error": str(exc)[:200]}
    if resp.status_code >= 400:
        return {"state": "unknown", "runs": [], "error": f"{resp.status_code}"}
    runs = [
        {
            "name": run.get("name"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "url": run.get("html_url"),
            "updated_at": run.get("updated_at"),
        }
        for run in resp.json().get("workflow_runs", [])
    ]
    if not runs:
        state = "queued"
    elif any(r["status"] != "completed" for r in runs):
        state = "building"
    elif all(r["conclusion"] == "success" for r in runs):
        state = "success"
    else:
        state = "failed"
    return {"state": state, "runs": runs}


def read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
