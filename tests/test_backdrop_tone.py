"""Every render of a set takes one reference's studio field
(studio.normalize.match_background_tone): a recolour repainted the wall with
the upholstery — cream on beige, silver on grey."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from test_geometry_lock import CREAM, TAUPE, _bed

IVORY, BEIGE = (244, 242, 238), (228, 220, 200)


def _corner_wall(path: Path) -> np.ndarray:
    """Mean RGB of the empty top-left wall."""
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32)[20:120, 20:200].reshape(-1, 3).mean(0)


def test_drifted_wall_takes_the_references_tone(server, tmp_path):
    from studio.normalize import match_background_tone
    ref = tmp_path / "ref.png"
    _bed(CREAM, wall=IVORY).save(ref)
    variant = tmp_path / "variant.png"
    _bed(TAUPE, wall=BEIGE).save(variant)
    before = np.asarray(Image.open(variant).convert("RGB")).astype(np.float32)

    _, applied = match_background_tone(variant, ref)
    assert applied
    assert np.abs(_corner_wall(variant) - _corner_wall(ref)).max() <= 2.0
    # The upholstery barely moves: the target is the wall, not the product.
    # (Product pixels located on a green-wall drawing of the same bed.)
    after = np.asarray(Image.open(variant).convert("RGB")).astype(np.float32)
    marker = np.asarray(_bed(TAUPE, wall=(90, 200, 90))).astype(np.int32)
    product = np.abs(marker - np.array(TAUPE)).max(axis=2) < 6
    assert np.abs(after - before)[product].mean() <= 3.5


def test_reference_of_another_size_still_sets_the_tone(server, tmp_path):
    """Seria's reference is the uploaded source, rarely the render's size."""
    from studio.normalize import match_background_tone
    ref = tmp_path / "ref.png"
    _bed(TAUPE, wall=IVORY).resize((384, 480)).save(ref)
    variant = tmp_path / "variant.png"
    _bed(CREAM, wall=BEIGE).save(variant)
    _, applied = match_background_tone(variant, ref)
    assert applied and np.abs(_corner_wall(variant) - np.array(IVORY)).max() <= 3.0


def _room(size=(768, 960)) -> Image.Image:
    """Windows, frames, plants and a rug: the frame border is busy."""
    rng = np.random.default_rng(7)
    arr = np.full((size[1], size[0], 3), 200, np.float32)
    for _ in range(400):
        x, y = rng.integers(0, size[0] - 60), rng.integers(0, size[1] - 60)
        arr[y:y + 60, x:x + 60] = rng.integers(40, 250, 3)
    return Image.fromarray(arr.astype(np.uint8))


@pytest.mark.parametrize("pair", ["room_reference", "room_variant", "already_matching"])
def test_untouched_when_not_a_studio_sweep_or_already_matching(server, tmp_path, pair):
    from studio.normalize import match_background_tone
    ref, variant = tmp_path / "ref.png", tmp_path / "variant.png"
    (_room() if pair == "room_reference" else _bed(TAUPE, wall=IVORY)).save(ref)
    (_room() if pair == "room_variant" else _bed(CREAM, wall=IVORY)).save(variant)
    before = variant.read_bytes()
    _, applied = match_background_tone(variant, ref)
    assert not applied and variant.read_bytes() == before


# --------------------------------------------------------------------------
# Routes: Warianty (anchor), Seria and its per-tile regenerate (the source)
# --------------------------------------------------------------------------
@pytest.fixture()
def routes(server, monkeypatch, base_image):
    from app.core.generator import GenerationResult
    from studio import routes_generate

    seen = {"tone": [], "geometry": []}

    def fake_render(req, openai_key="", quality="", openrouter_key=""):
        out = Path(base_image).parent / f"r{len(seen['tone'])}-{id(req)}.png"
        Image.new("RGB", (64, 48), (200, 190, 180)).save(out)
        return GenerationResult(
            success=True, generation_id="g", output_path=out, output_image=Image.open(out),
            next_history=[], actual_cost=0.01, attempts=1, error_message=None,
            model_id=req.model_id, resolution="1K",
        )

    monkeypatch.setattr(routes_generate, "_render_product", fake_render)
    monkeypatch.setattr(routes_generate, "normalize_packshot", lambda path, profile: (path, False))
    monkeypatch.setattr(routes_generate, "match_anchor_geometry",
                        lambda m, a: (seen["geometry"].append((Path(m), Path(a))), (m, True))[1])
    monkeypatch.setattr(routes_generate, "match_background_tone",
                        lambda m, r: (seen["tone"].append((Path(m), Path(r))), (m, True))[1])
    return seen


def _client(server):
    from fastapi.testclient import TestClient
    return TestClient(server.app)


def _set(server, base_image, **fields):
    data = {"api_key": "AIza-test", "kind": "bed", "mat": "cremona", "size": "160",
            "colors_csv": "taupe,cream,graphite", "shot": "hero", **fields}
    return _client(server).post("/api/generate-set", data=data,
                                files={"base_image": ("base.png", base_image.read_bytes(), "image/png")})


@pytest.mark.parametrize("background", ["ivory", "grey"])
def test_warianty_on_any_studio_backdrop_lock_the_tone_to_the_anchor(server, base_image, routes, background):
    r = _set(server, base_image, background=background)
    assert r.status_code == 200, r.text
    assert len(routes["tone"]) == 2 and len({ref for _, ref in routes["tone"]}) == 1
    assert all(v["tone_locked"] for v in r.json()["variants"])
    # Geometry stays a locked-backdrop thing: ivory is locked, grey is not.
    assert len(routes["geometry"]) == (2 if background == "ivory" else 0)


@pytest.mark.parametrize("fields", [{"background": "scandi"}, {"background": "ivory", "shot": "close_up"}])
def test_warianty_in_a_room_or_on_a_tight_shot_keep_their_tone(server, base_image, routes, fields):
    r = _set(server, base_image, **fields)
    assert r.status_code == 200, r.text
    assert routes["tone"] == []


def test_seria_tiles_and_regenerate_take_the_sources_tone(server, base_image, routes):
    client = _client(server)
    pairs = [{"color": "cream", "material": "boucle"}, {"color": "taupe", "material": "boucle"}]
    r = client.post("/api/generate-variants",
                    data={"api_key": "AIza-test", "kind": "bed", "pairs_json": json.dumps(pairs),
                          "upload_sids_csv": "s1"},
                    files=[("sources", ("src.png", base_image.read_bytes(), "image/png"))])
    assert r.status_code == 200, r.text
    tiles = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    tiles = [t for t in tiles if t.get("type") == "tile"]
    assert len(tiles) == 2 and all(t["tone_locked"] for t in tiles)
    assert len(routes["tone"]) == 2 and len({ref for _, ref in routes["tone"]}) == 1
    source = routes["tone"][0][1]
    assert all(master != source for master, _ in routes["tone"])

    r = client.post("/api/regenerate-variant",
                    data={"api_key": "AIza-test", "kind": "bed", "color": "graphite", "material": "boucle"},
                    files={"source_image": ("src.png", base_image.read_bytes(), "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["tone_locked"] and len(routes["tone"]) == 3
