"""Endpoint smoke tests — no external API calls, no API key required."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(server):
    return TestClient(server.app)


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["model_ids"], "model catalogue empty"


def test_index_serves_built_frontend(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "/assets/" in r.text, "index.html does not reference hashed assets"


@pytest.mark.parametrize("route", ["/video", "/help", "/admin", "/experiments"])
def test_secondary_pages(client, route):
    r = client.get(route)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_admin_catalog_is_local_and_reports_references(client):
    r = client.get("/api/admin/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["catalog"]["materials"]
    assert body["catalog"]["colors"]
    assert set(body["references"]) == {m["id"] for m in body["catalog"]["materials"]}
    assert body["build"]["state"]


def test_catalog_js(client):
    r = client.get("/catalog.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert r.text.startswith("window.NS_CATALOG = ")
    assert "chenille" in r.text


def test_api_config(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    models = r.json()["models"]
    assert models, "no models exposed"
    for m in models:
        assert m["id"]
        assert m["max_refs"] >= 1
        assert m["resolutions"]


def test_param_docs(client):
    r = client.get("/api/param-docs")
    assert r.status_code == 200
    groups = r.json()["groups"]
    assert groups, "param docs empty"
    keys = {g["key"] for g in groups}
    assert len(keys) == len(groups), "duplicate param-doc group keys"


def test_experiments_api_exposes_comparison_history(client):
    r = client.get("/api/experiments?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"items", "tracked_count", "legacy_count"}
    assert isinstance(body["items"], list)
    if body["items"]:
        item = body["items"][0]
        assert "generation_id" in item
        assert "tracked" in item
        assert "image_url" in item


def test_html_pages_revalidate_after_deploy(client):
    """Each entry page must carry no-cache so a fresh image is picked up on
    the next visit (a stale cached HTML kept pointing at old assets)."""
    for path in ("/", "/video", "/editorial", "/lab", "/experiments", "/admin", "/help"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.headers.get("cache-control") == "no-cache", path


def test_frame_set_zip_packs_outputs_under_download_names(server, monkeypatch, tmp_path):
    """"Pobierz zestaw": one ZIP of the set's renders, named like the single
    download, de-duplicated, and limited to files directly in the outputs dir."""
    import io
    import zipfile
    from fastapi.testclient import TestClient
    from studio import routes_pages
    monkeypatch.setattr(routes_pages, "_OUTPUT_DIR", tmp_path.resolve())
    (tmp_path / "a.jpg").write_bytes(b"AAA")
    (tmp_path / "b.jpg").write_bytes(b"BBB")
    client = TestClient(server.app)
    r = client.post("/api/outputs/zip", json={"zip_name": "zestaw.zip", "files": [
        {"url": "/api/outputs/a.jpg", "filename": "nano-sofa-front-x.jpg"},
        {"url": "/api/outputs/b.jpg", "filename": "nano-sofa-front-x.jpg"},
    ]})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert 'filename="zestaw.zip"' in r.headers["content-disposition"]
    archive = zipfile.ZipFile(io.BytesIO(r.content))
    assert archive.namelist() == ["nano-sofa-front-x.jpg", "nano-sofa-front-x-2.jpg"]
    assert archive.read("nano-sofa-front-x-2.jpg") == b"BBB"
    # Traversal and unknown files are refused, like /api/outputs/{name}.
    (tmp_path.parent / "secret.jpg").write_bytes(b"S")
    r = client.post("/api/outputs/zip", json={"files": [{"url": "/api/outputs/../secret.jpg"}]})
    assert r.status_code == 404
    assert client.post("/api/outputs/zip", json={"files": []}).status_code == 400
