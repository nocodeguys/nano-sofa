"""Catalogue admin validation and transactional save tests."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def test_catalog_reload_preserves_imported_mapping_identity(server):
    from studio.catalog import (
        CATALOG,
        _COLOR_PL_TO_EN,
        reload_catalog,
    )

    original = json.loads(json.dumps(CATALOG))
    mapping_identity = id(_COLOR_PL_TO_EN)
    changed = json.loads(json.dumps(original))
    changed["colors"][0]["prompt_en"] = "temporary admin test colour"
    try:
        reload_catalog(changed)
        assert id(_COLOR_PL_TO_EN) == mapping_identity
        assert _COLOR_PL_TO_EN[changed["colors"][0]["id"]] == "temporary admin test colour"
        assert server._COLOR_PL_TO_EN[changed["colors"][0]["id"]] == "temporary admin test colour"
    finally:
        reload_catalog(original)


def test_admin_save_builds_staged_frontend_and_promotes_catalog(server, tmp_path, monkeypatch):
    from studio import routes_admin
    from studio.catalog import CATALOG, reload_catalog

    original = json.loads(json.dumps(CATALOG))
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(original), encoding="utf-8")
    frontend = tmp_path / "frontend"
    dist = frontend / "dist"
    refs = tmp_path / "material-references"
    backups = tmp_path / "backups"
    dist.mkdir(parents=True)
    refs.mkdir()
    backups.mkdir()
    (dist / "index.html").write_text("old index", encoding="utf-8")
    (dist / "admin.html").write_text("old admin", encoding="utf-8")

    def fake_build(staging_dist: Path) -> str:
        staging_dist.mkdir(parents=True)
        (staging_dist / "index.html").write_text("new index", encoding="utf-8")
        (staging_dist / "admin.html").write_text("new admin", encoding="utf-8")
        return "test build ok"

    monkeypatch.setattr(routes_admin, "_CATALOG_PATH", catalog_path)
    monkeypatch.setattr(routes_admin, "_FRONTEND_DIR", frontend)
    monkeypatch.setattr(routes_admin, "_DIST_DIR", dist)
    monkeypatch.setattr(routes_admin, "_MATERIAL_REFS_DIR", refs)
    monkeypatch.setattr(routes_admin, "_CATALOG_BACKUPS_DIR", backups)
    monkeypatch.setattr(routes_admin, "_build_frontend", fake_build)

    changed = json.loads(json.dumps(original))
    changed["colors"][0]["name_pl"] = "kolor testowy"
    client = TestClient(server.app)
    try:
        response = client.post(
            "/api/admin/catalog",
            data={
                "catalog_json": json.dumps(changed),
                "delete_reference_ids_json": "[]",
            },
        )
        assert response.status_code == 200, response.text
        assert json.loads(catalog_path.read_text())["colors"][0]["name_pl"] == "kolor testowy"
        assert (dist / "index.html").read_text() == "new index"
        assert list(backups.glob("catalog-*.zip"))
        assert CATALOG["colors"][0]["name_pl"] == "kolor testowy"
    finally:
        reload_catalog(original)


def test_admin_rejects_invalid_hex_without_building(server, monkeypatch):
    from studio import routes_admin
    from studio.catalog import CATALOG

    called = False

    def forbidden_build(_staging_dist: Path) -> str:
        nonlocal called
        called = True
        return ""

    monkeypatch.setattr(routes_admin, "_build_frontend", forbidden_build)
    changed = json.loads(json.dumps(CATALOG))
    changed["colors"][0]["hex"] = "ivory"
    response = TestClient(server.app).post(
        "/api/admin/catalog",
        data={"catalog_json": json.dumps(changed), "delete_reference_ids_json": "[]"},
    )
    assert response.status_code == 422
    assert "#RRGGBB" in response.json()["detail"]
    assert called is False
