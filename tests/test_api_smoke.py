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


@pytest.mark.parametrize("route", ["/video", "/help"])
def test_secondary_pages(client, route):
    r = client.get(route)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


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
