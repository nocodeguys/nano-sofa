"""The one place model facts come from: app-v2/models.json.

Everything that used to hard-code a model id, a reference cap, a price or a
"is it Pro?" substring test reads this module instead. The registry is plain
data; this module only loads it, validates the shape we rely on, and offers
the handful of lookups the server, the cost tracker and the engines need.

Engines: "gemini" (google-genai, app/core/generator.py), "openai"
(studio/openai_images.py), "openrouter" (studio/openrouter.py).
Surfaces: "studio" (product wizard), "lab" (product wizard on OpenAI),
"editorial" (freeform).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = _REPO_ROOT / "app-v2" / "models.json"

ENGINES = ("gemini", "openai", "openrouter")
SURFACES = ("studio", "lab", "editorial", "meli")
RESOLUTION_ORDER = ["1K", "2K", "4K"]


@dataclass(frozen=True)
class Model:
    id: str
    engine: str
    provider: str
    label: str
    short: str
    tier: str
    status: str                      # "active" | "deprecated"
    surfaces: tuple[str, ...]
    max_refs: int
    resolutions: tuple[str, ...]     # ("1K","2K","4K") or ("auto",)
    supports_resolution_param: bool
    aspects: tuple[str, ...]
    qualities: tuple[str, ...] = ()
    default_quality: str = ""
    input_fidelity: bool = False
    product: bool = False            # OpenRouter: may run the Lab product wizard
    thinking: dict[str, Any] = field(default_factory=dict)
    pricing: dict[str, Any] = field(default_factory=dict)
    deprecation: Optional[dict[str, Any]] = None
    note_pl: str = ""
    snapshot: str = ""

    @property
    def deprecated(self) -> bool:
        return self.status != "active"

    @property
    def max_resolution(self) -> str:
        return self.resolutions[-1] if self.resolutions else "1K"

    def resolution_choices(self) -> list[str]:
        if self.resolutions == ("auto",):
            return ["auto"]
        ceiling = self.max_resolution
        cutoff = RESOLUTION_ORDER.index(ceiling) if ceiling in RESOLUTION_ORDER else 0
        return RESOLUTION_ORDER[: cutoff + 1]

    def price_per_image(self, resolution: str = "1K", batch: bool = False) -> float:
        """Best-known USD per generated image at that resolution (0 if unknown)."""
        key = "output_image_batch" if batch else "output_image"
        table = self.pricing.get(key) or self.pricing.get("output_image") or {}
        res = (resolution or "1K").split(" ")[0].upper()
        return float(table.get(res, table.get("1K", 0.0)) or 0.0)

    def to_config(self) -> dict[str, Any]:
        """Shape served by /api/config — everything the UI needs, nothing else."""
        return {
            "id": self.id,
            "label": self.label,
            "short": self.short,
            "tier": self.tier,
            "engine": self.engine,
            "provider": self.provider,
            "deprecated": self.deprecated,
            "product": self.product,
            "max_refs": self.max_refs,
            "moodboard_max": 3 if self.engine == "gemini" else max(1, min(6, self.max_refs)),
            "max_resolution": self.max_resolution,
            "supports_resolution_param": self.supports_resolution_param,
            "resolutions": self.resolution_choices(),
            "aspects": list(self.aspects),
            "qualities": list(self.qualities),
            "default_quality": self.default_quality,
            "price_hint": self.pricing.get("price_hint", ""),
            "pricing": {r: self.price_per_image(r) for r in self.resolution_choices() if r != "auto"},
            "note": self.note_pl,
        }


class ModelRegistry:
    def __init__(self, path: Path = REGISTRY_PATH) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.defaults: dict[str, str] = dict(raw["defaults"])
        self.eta_seed: dict[str, dict[str, list[float]]] = raw.get("eta_seed", {})
        self.models: dict[str, Model] = {}
        for entry in raw["models"]:
            m = Model(
                id=entry["id"], engine=entry["engine"], provider=entry.get("provider", entry["engine"]),
                label=entry["label"], short=entry.get("short", entry["label"]),
                tier=entry.get("tier", "other"), status=entry.get("status", "active"),
                surfaces=tuple(entry.get("surfaces", ())),
                max_refs=int(entry["max_refs"]),
                resolutions=tuple(entry.get("resolutions") or ["1K"]),
                supports_resolution_param=bool(entry.get("supports_resolution_param", False)),
                aspects=tuple(entry.get("aspects") or ()),
                qualities=tuple(entry.get("qualities") or ()),
                default_quality=entry.get("default_quality", ""),
                input_fidelity=bool(entry.get("input_fidelity", False)),
                product=bool(entry.get("product", False)),
                thinking=dict(entry.get("thinking") or {}),
                pricing=dict(entry.get("pricing") or {}),
                deprecation=entry.get("deprecation"),
                note_pl=entry.get("note_pl", ""),
                snapshot=entry.get("snapshot", ""),
            )
            if m.engine not in ENGINES:
                raise ValueError(f"models.json: {m.id}: unknown engine {m.engine!r}")
            if m.id in self.models:
                raise ValueError(f"models.json: duplicate id {m.id!r}")
            self.models[m.id] = m
        for surface, mid in self.defaults.items():
            if surface not in SURFACES:
                raise ValueError(f"models.json: unknown surface {surface!r} in defaults")
            m = self.models.get(mid)
            if m is None or m.deprecated or surface not in m.surfaces:
                raise ValueError(
                    f"models.json: default for {surface!r} must be an active model offered there: {mid!r}"
                )

    # ---- lookups ------------------------------------------------------- #
    def get(self, model_id: str) -> Optional[Model]:
        return self.models.get((model_id or "").strip())

    def __contains__(self, model_id: str) -> bool:
        return self.get(model_id) is not None

    def engine_of(self, model_id: str) -> str:
        """Engine for an id; unknown ids go to gemini, which is where they
        would have gone before the registry existed (and where the API
        answers with a proper model-not-found)."""
        m = self.get(model_id)
        return m.engine if m else "gemini"

    def product_models(self, engine: str) -> dict[str, Model]:
        """External models allowed in the Lab product wizard."""
        return {m.id: m for m in self.models.values() if m.engine == engine and m.product}

    def by_engine(self, engine: str, *, include_deprecated: bool = True) -> list[Model]:
        return [m for m in self.models.values()
                if m.engine == engine and (include_deprecated or not m.deprecated)]

    def for_surface(self, surface: str, *, include_deprecated: bool = True) -> list[Model]:
        return [m for m in self.models.values()
                if surface in m.surfaces and (include_deprecated or not m.deprecated)]

    def default_for(self, surface: str) -> str:
        return self.defaults[surface]

    def resolve(self, model_id: str, surface: str) -> str:
        """Empty form field → that surface's default; anything else as given."""
        return (model_id or "").strip() or self.default_for(surface)

    def max_refs(self, model_id: str, fallback: int = 3) -> int:
        m = self.get(model_id)
        return m.max_refs if m else fallback

    def tier_of(self, model_id: str) -> str:
        m = self.get(model_id)
        return m.tier if m else "flash"

    def eta_seed_for(self, model_id: str, resolution: str) -> tuple[float, float]:
        tier = self.tier_of(model_id)
        table = self.eta_seed.get(tier) or self.eta_seed.get("flash") or {}
        res = (resolution or "1K").split(" ")[0].upper()
        p50, p90 = table.get(res) or table.get("1K") or [12.0, 24.0]
        return float(p50), float(p90)

    def config_payload(self) -> dict[str, Any]:
        """/api/config body. Deprecated models are listed (old presets must
        still resolve) but flagged, and never the default."""
        studio = [m.to_config() for m in self.for_surface("studio")]
        lab = [m.to_config() for m in self.for_surface("lab")]
        editorial = [m.to_config() for m in self.for_surface("editorial")]
        return {
            "models": studio,
            "default_model": self.default_for("studio"),
            "editorial_models": editorial,
            "editorial_default_model": self.default_for("editorial"),
            "lab_models": lab,
            "lab_default_model": self.default_for("lab"),
            "eta_seed": self.eta_seed,
        }


registry: ModelRegistry = ModelRegistry()


def reload() -> ModelRegistry:
    global registry
    registry = ModelRegistry()
    return registry
