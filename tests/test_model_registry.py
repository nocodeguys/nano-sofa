"""app-v2/models.json is the only place a model id, cap or price may live.

The grep test is the point: the diagnosis found model ids in eight files and
"is it Pro?" decided by substring in ten places. Nothing stops that from
creeping back except a test that reads the source tree.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core import cost_tracker
from app.core.model_registry import ModelRegistry, registry

REPO_ROOT = Path(__file__).resolve().parent.parent

# Anything that looks like one of our image-model ids, in code only.
_ID_PATTERN = re.compile(
    r"gemini-[0-9a-z.\-]*(?:image|banana)[0-9a-z.\-]*"
    r"|gpt-image-[0-9a-z.\-]+"
    r"|(?:bytedance-seed|black-forest-labs|krea)/[0-9a-z.\-]+"
)
_SOURCE_DIRS = (
    REPO_ROOT / "app",
    REPO_ROOT / "app-v2" / "studio",
    REPO_ROOT / "app-v2" / "server.py",
    REPO_ROOT / "app-v2" / "frontend" / "src",
)
_ALLOWED = {REPO_ROOT / "app-v2" / "models.json"}


def _source_files():
    for root in _SOURCE_DIRS:
        if root.is_file():
            yield root
            continue
        for path in root.rglob("*"):
            if path.suffix in (".py", ".js", ".jsx", ".json") and "node_modules" not in path.parts:
                yield path


def _strip_comments(path: Path, text: str) -> str:
    if path.suffix == ".py":
        return "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    if path.suffix in (".js", ".jsx"):
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return "\n".join(line.split("//", 1)[0] for line in text.splitlines())
    return text


def test_no_model_id_literal_outside_the_registry():
    offenders = []
    for path in _source_files():
        if path in _ALLOWED or path.name == "video_generator.py":
            continue
        code = _strip_comments(path, path.read_text(encoding="utf-8", errors="ignore"))
        for m in _ID_PATTERN.finditer(code):
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {m.group(0)}")
    assert not offenders, "model ids outside app-v2/models.json:\n  " + "\n  ".join(offenders)


def test_registry_loads_and_defaults_are_sane():
    for surface in ("studio", "lab", "editorial"):
        mid = registry.default_for(surface)
        m = registry.get(mid)
        assert m is not None and not m.deprecated and surface in m.surfaces


def test_every_gemini_model_has_full_pricing():
    for m in registry.by_engine("gemini"):
        for res in ("1K", "2K", "4K"):
            assert m.price_per_image(res) > 0, (m.id, res)
            assert m.price_per_image(res, batch=True) > 0, (m.id, res)
        assert m.pricing.get("text_input_per_1m"), m.id
        assert m.pricing.get("input_image_tokens"), m.id
        assert m.id in cost_tracker.OUTPUT_IMAGE_PRICE_STD
        assert m.id in cost_tracker.INPUT_IMAGE_TOKEN_COST


def test_engine_views_match_registry():
    from studio.openai_images import OPENAI_MODELS
    from studio.openrouter import OPENROUTER_MODELS
    assert set(OPENAI_MODELS) == {m.id for m in registry.by_engine("openai")}
    assert set(OPENROUTER_MODELS) == {m.id for m in registry.by_engine("openrouter")}
    for mid, cfg in {**OPENAI_MODELS, **OPENROUTER_MODELS}.items():
        assert cfg["max_refs"] == registry.get(mid).max_refs


def test_engine_of_and_resolve():
    assert registry.engine_of(registry.default_for("studio")) == "gemini"
    assert registry.engine_of(registry.default_for("lab")) == "openai"
    assert registry.engine_of("openai/gpt-image-2") == "openrouter"
    assert registry.engine_of("made-up-model") == "gemini"
    assert registry.resolve("", "studio") == registry.default_for("studio")
    assert registry.resolve("  x ", "studio") == "x"


def test_eta_seed_uses_tier_not_substring():
    pro = next(m for m in registry.by_engine("gemini") if m.tier == "pro")
    flash = registry.get(registry.default_for("studio"))
    assert registry.eta_seed_for(pro.id, "1K")[0] > registry.eta_seed_for(flash.id, "1K")[0]
    est = cost_tracker.estimate_duration(pro.id, "2K", 3)
    assert est["p50_s"] > cost_tracker.estimate_duration(flash.id, "2K", 3)["p50_s"]


def test_bad_registry_is_rejected(tmp_path):
    bad = tmp_path / "models.json"
    bad.write_text('{"defaults": {"studio": "nope"}, "models": []}')
    with pytest.raises(ValueError):
        ModelRegistry(bad)
