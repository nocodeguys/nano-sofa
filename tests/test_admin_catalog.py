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


def _isolate_admin_paths(routes_admin, monkeypatch, tmp_path, original):
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(original), encoding="utf-8")
    refs = tmp_path / "material-references"
    backups = tmp_path / "backups"
    refs.mkdir()
    backups.mkdir()
    monkeypatch.setattr(routes_admin, "_CATALOG_PATH", catalog_path)
    monkeypatch.setattr(routes_admin, "_MATERIAL_REFS_DIR", refs)
    monkeypatch.setattr(routes_admin, "_CATALOG_BACKUPS_DIR", backups)
    monkeypatch.setattr(routes_admin, "_PENDING_PUSH_PATH", tmp_path / "pending-push.json")
    monkeypatch.setattr(routes_admin, "_LAST_PUSH_PATH", tmp_path / "last-push.json")
    monkeypatch.delenv("CATALOG_GIT_TOKEN", raising=False)
    return catalog_path, refs, backups


def test_admin_save_promotes_catalog_without_frontend_build(server, tmp_path, monkeypatch):
    from studio import routes_admin
    from studio.catalog import CATALOG, reload_catalog

    original = json.loads(json.dumps(CATALOG))
    catalog_path, refs, backups = _isolate_admin_paths(routes_admin, monkeypatch, tmp_path, original)

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
        # Photos are normalised to JPEG so a save doesn't add a 20 MB PNG to the repo.
        assert (refs / f"{material_id}-application.jpg").is_file()
        assert (refs / f"{material_id}-left.jpg").is_file()
        assert response.json()["application_references"][material_id]["exists"]
        assert response.json()["view_references"][material_id]["left"]["exists"]
        application_response = client.get(
            f"/api/admin/material-application-reference/{material_id}"
        )
        assert application_response.status_code == 200
        assert application_response.headers["content-type"] == "image/jpeg"
        angle_response = client.get(
            f"/api/admin/material-view-reference/left/{material_id}"
        )
        assert angle_response.status_code == 200
        assert angle_response.headers["content-type"] == "image/jpeg"
        # No CATALOG_GIT_TOKEN in tests → the edit is recorded as local-only.
        assert response.json()["git"]["enabled"] is False
        assert response.json()["git"]["pending"]["reason"] == "not_configured"
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


def test_admin_requires_token_when_configured(server, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret-token")
    client = TestClient(server.app)
    # The page itself is static and always served; the API behind it is gated.
    assert client.get("/admin").status_code == 200
    denied = client.get("/api/admin/catalog")
    assert denied.status_code == 401
    assert "ADMIN_TOKEN" in denied.json()["detail"]
    wrong = client.get("/api/admin/catalog", headers={"X-Admin-Token": "nope"})
    assert wrong.status_code == 401
    ok = client.get("/api/admin/catalog", headers={"X-Admin-Token": "s3cret-token"})
    assert ok.status_code == 200
    bearer = client.get("/api/admin/catalog", headers={"Authorization": "Bearer s3cret-token"})
    assert bearer.status_code == 200
    assert "known_tex" in ok.json() and "git" in ok.json()


def test_admin_without_token_is_loopback_only(server, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    client = TestClient(server.app)  # peer host "testclient" counts as local
    assert client.get("/api/admin/catalog").status_code == 200
    remote = TestClient(server.app, client=("172.18.0.1", 51000))
    denied = remote.get("/api/admin/catalog")
    assert denied.status_code == 403
    assert "ADMIN_TOKEN" in denied.json()["detail"]


def test_seed_refreshes_runtime_catalog_when_image_changes(server, tmp_path):
    from studio.paths import _seed_runtime_catalog

    bundled_catalog = tmp_path / "bundled.json"
    bundled_catalog.write_text('{"version": 1}', encoding="utf-8")
    bundled_refs = tmp_path / "bundled-references"
    bundled_refs.mkdir()
    (bundled_refs / "fabric.jpg").write_bytes(b"first")
    output_dir = tmp_path / "outputs"

    catalog_path, refs_path = _seed_runtime_catalog(
        output_dir, bundled_catalog, bundled_refs, build_sha="aaaa111"
    )
    assert (output_dir / "catalog" / ".seed-sha").read_text().strip() == "aaaa111"

    # Same image again: runtime edits survive.
    catalog_path.write_text('{"version": 99}', encoding="utf-8")
    _seed_runtime_catalog(output_dir, bundled_catalog, bundled_refs, build_sha="aaaa111")
    assert catalog_path.read_text() == '{"version": 99}'

    # New image, nothing pending: bundled files win, previous copy kept.
    bundled_catalog.write_text('{"version": 2}', encoding="utf-8")
    (bundled_refs / "fabric.jpg").write_bytes(b"second")
    _seed_runtime_catalog(output_dir, bundled_catalog, bundled_refs, build_sha="bbbb222")
    assert catalog_path.read_text() == '{"version": 2}'
    assert (refs_path / "fabric.jpg").read_bytes() == b"second"
    assert (output_dir / "catalog" / "previous" / "catalog.json").read_text() == '{"version": 99}'

    # New image but edits waiting to be pushed: runtime copy is kept.
    catalog_path.write_text('{"version": 100}', encoding="utf-8")
    (output_dir / "catalog" / "pending-push.json").write_text("{}", encoding="utf-8")
    bundled_catalog.write_text('{"version": 3}', encoding="utf-8")
    _seed_runtime_catalog(output_dir, bundled_catalog, bundled_refs, build_sha="cccc333")
    assert catalog_path.read_text() == '{"version": 100}'


def test_collections_are_validated_and_flattened(server):
    from studio import routes_admin
    from studio.catalog import CATALOG, flatten_colors

    changed = json.loads(json.dumps(CATALOG))
    changed["collections"] = [{
        "id": "velutto", "name_pl": "Velutto", "material": "velour",
        "codes": [{"code": "27", "hex": "#122d24"}, {"code": "6", "hex": "#29231D", "name_pl": "Velutto 6"}],
    }]
    normalized = routes_admin.validate_catalog(changed)
    codes = normalized["collections"][0]["codes"]
    assert codes[0]["hex"] == "#122D24"
    assert codes[0]["name_pl"] == "Velutto 27"
    assert "#122D24" in codes[0]["prompt_en"]
    flat = {c["id"]: c for c in flatten_colors(normalized)}
    assert flat["velutto-27"]["material"] == "velour"
    assert flat["velutto-27"]["fabric_code"] == "Velutto 27"
    assert flat["velutto-6"]["hex"] == "#29231D"

    bad_material = json.loads(json.dumps(changed))
    bad_material["collections"][0]["material"] = "silk"
    try:
        routes_admin.validate_catalog(bad_material)
    except ValueError as exc:
        assert "silk" in str(exc)
    else:
        raise AssertionError("unknown collection material accepted")

    clash = json.loads(json.dumps(changed))
    clash["colors"].append({"id": "velutto-27", "name_pl": "x", "hex": "#000000", "prompt_en": "x"})
    try:
        routes_admin.validate_catalog(clash)
    except ValueError as exc:
        assert "velutto-27" in str(exc)
    else:
        raise AssertionError("flattened id clash accepted")


def test_catalog_js_carries_the_flattened_color_index(server):
    body = TestClient(server.app).get("/catalog.js").text
    assert body.startswith("window.NS_CATALOG = ")
    assert '"color_index"' in body
    assert '"velutto-27"' in body
