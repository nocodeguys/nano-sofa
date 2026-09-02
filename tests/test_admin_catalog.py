"""Catalogue admin validation and transactional save tests."""
from __future__ import annotations

import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image


def test_runtime_catalog_seed_is_persistent_and_non_destructive(server, tmp_path):
    from studio.paths import _seed_runtime_catalog

    bundled_catalog = tmp_path / "bundled.json"
    bundled_catalog.write_text('{"version": 1}', encoding="utf-8")
    bundled_refs = tmp_path / "bundled-references"
    bundled_refs.mkdir()
    (bundled_refs / "fabric.jpg").write_bytes(b"first")
    output_dir = tmp_path / "outputs"

    catalog_path, refs_path = _seed_runtime_catalog(
        output_dir, bundled_catalog, bundled_refs
    )
    catalog_path.write_text('{"version": 99}', encoding="utf-8")
    (refs_path / "fabric.jpg").write_bytes(b"edited")
    bundled_catalog.write_text('{"version": 2}', encoding="utf-8")
    (bundled_refs / "fabric.jpg").write_bytes(b"second")

    next_catalog, next_refs = _seed_runtime_catalog(
        output_dir, bundled_catalog, bundled_refs
    )
    assert next_catalog.read_text(encoding="utf-8") == '{"version": 99}'
    assert (next_refs / "fabric.jpg").read_bytes() == b"edited"


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


def test_admin_save_promotes_catalog_without_frontend_build(server, tmp_path, monkeypatch):
    from studio import routes_admin
    from studio.catalog import CATALOG, reload_catalog

    original = json.loads(json.dumps(CATALOG))
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(original), encoding="utf-8")
    refs = tmp_path / "material-references"
    backups = tmp_path / "backups"
    refs.mkdir()
    backups.mkdir()

    monkeypatch.setattr(routes_admin, "_CATALOG_PATH", catalog_path)
    monkeypatch.setattr(routes_admin, "_MATERIAL_REFS_DIR", refs)
    monkeypatch.setattr(routes_admin, "_CATALOG_BACKUPS_DIR", backups)

    changed = json.loads(json.dumps(original))
    changed["colors"][0]["name_pl"] = "kolor testowy"
    material_id = changed["materials"][0]["id"]
    application_image = io.BytesIO()
    Image.new("RGB", (256, 192), (180, 170, 160)).save(
        application_image,
        format="PNG",
    )
    angle_image = io.BytesIO()
    Image.new("RGB", (192, 256), (210, 205, 195)).save(
        angle_image,
        format="JPEG",
    )
    client = TestClient(server.app)
    try:
        response = client.post(
            "/api/admin/catalog",
            data={
                "catalog_json": json.dumps(changed),
                "delete_reference_ids_json": "[]",
                "application_reference_ids": material_id,
                "delete_application_reference_ids_json": "[]",
                "view_reference_keys": f"{material_id}:left",
                "delete_view_reference_keys_json": "[]",
            },
            files=[
                ("application_reference_files", (
                    "competitor-bed.png",
                    application_image.getvalue(),
                    "image/png",
                )),
                ("view_reference_files", (
                    "left-angle.jpg",
                    angle_image.getvalue(),
                    "image/jpeg",
                )),
            ],
        )
        assert response.status_code == 200, response.text
        assert json.loads(catalog_path.read_text())["colors"][0]["name_pl"] == "kolor testowy"
        assert (refs / f"{material_id}-application.png").is_file()
        assert (refs / f"{material_id}-left.png").is_file()
        assert response.json()["application_references"][material_id]["exists"]
        assert response.json()["view_references"][material_id]["left"]["exists"]
        application_response = client.get(
            f"/api/admin/material-application-reference/{material_id}"
        )
        assert application_response.status_code == 200
        assert application_response.headers["content-type"] == "image/png"
        angle_response = client.get(
            f"/api/admin/material-view-reference/left/{material_id}"
        )
        assert angle_response.status_code == 200
        assert angle_response.headers["content-type"] == "image/png"
        assert list(backups.glob("catalog-*.zip"))
        assert CATALOG["colors"][0]["name_pl"] == "kolor testowy"
    finally:
        reload_catalog(original)


def test_admin_rejects_invalid_hex_before_writing(server):
    from studio import routes_admin
    from studio.catalog import CATALOG

    changed = json.loads(json.dumps(CATALOG))
    changed["colors"][0]["hex"] = "ivory"
    response = TestClient(server.app).post(
        "/api/admin/catalog",
        data={"catalog_json": json.dumps(changed), "delete_reference_ids_json": "[]"},
    )
    assert response.status_code == 422
    assert "#RRGGBB" in response.json()["detail"]
