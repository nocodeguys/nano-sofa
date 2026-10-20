"""PromptSpec — the engine-agnostic description of one render.

Everything the prompt text can say comes from here; nothing in the sections
reads a GenerationRequest or a picker id. The spec is plain dataclasses so
it can be dumped into the trace (`to_dict`) and diffed between two runs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


# --------------------------------------------------------------------------
# Colour helpers (moved here from generator.py so the spec can judge
# "deep shade" without importing the engine module).
# --------------------------------------------------------------------------
def hex_to_rgb(value: str) -> Optional[tuple[int, int, int]]:
    text = (value or "").strip().lstrip("#")
    if len(text) != 6:
        return None
    try:
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return None


def relative_luminance(hex_value: str) -> Optional[float]:
    rgb = hex_to_rgb(hex_value)
    if rgb is None:
        return None

    def channel(value: int) -> float:
        c = value / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_dark_hex(hex_value: str) -> bool:
    lum = relative_luminance(hex_value)
    return lum is not None and lum < 0.11


# --------------------------------------------------------------------------
# Spec parts
# --------------------------------------------------------------------------
@dataclass
class ProductSpec:
    noun: str = "sofa"                     # "sofa" | "bed"
    configuration: str = ""                # size label ("3-seater", "160x200 queen")
    frame_style: Optional[str] = None      # bed-only
    leg_count: int = 4
    preserve: list[str] = field(default_factory=list)
    leg_id: Optional[str] = None
    leg_explicit_descriptor: str = ""
    leg_instruction: str = ""
    bedding: str = ""                      # bed-only styling paragraph

    @property
    def is_bed(self) -> bool:
        return self.noun == "bed"

    @property
    def legs_visible(self) -> bool:
        return self.leg_count > 0

    @property
    def has_leg_swap(self) -> bool:
        return bool(self.leg_id or self.leg_explicit_descriptor)


@dataclass
class MaterialSpec:
    noun: str = ""                         # English material noun
    spec: str = ""                         # texture spec (+ user notes)
    avoid: list[str] = field(default_factory=list)


@dataclass
class ColourSpec:
    text: str = ""                         # English colour phrase
    hex: str = ""                          # "#RRGGBB" or ""

    @property
    def dark(self) -> bool:
        return is_dark_hex(self.hex)

    @property
    def hex_upper(self) -> str:
        return (self.hex or "").strip().upper()


@dataclass
class CameraSpec:
    angle_label: str = "front-34-left"
    degrees: int = 35
    focal_mm: int = 50
    aperture: str = "f/4.5"
    framing: str = ""
    shot_type: str = "hero"
    lens_descriptor: str = ""
    height_phrase: str = ""                # freeform only
    preserve_from_base: bool = False

    @property
    def is_detail(self) -> bool:
        return self.shot_type in ("detail_fabric", "detail_corner")

    @property
    def is_close_up(self) -> bool:
        return self.shot_type == "close_up"

    @property
    def is_tight(self) -> bool:
        """Any crop into the product: close-up or macro detail."""
        return self.is_detail or self.is_close_up


@dataclass
class SceneSpec:
    mode: str = ""                         # "" | "packshot" | "lifestyle"
    description: str = ""
    tod: str = ""
    shadow_description: str = ""
    shadow_direction: str = ""
    keep_source_scene: bool = False
    contains_product: bool = False
    view_consistency: bool = False
    setting_text: str = ""                 # freeform SETTING
    light_text: str = ""                   # freeform LIGHT


@dataclass
class EditorialSpec:
    brief: str = ""
    art_direction: str = ""
    people_text: str = ""                  # resolved people clause, "" = none picked
    seed: str = ""


@dataclass
class PromptSpec:
    mode: str = "product"                  # "product" | "freeform"
    slots: dict[str, int] = field(default_factory=dict)   # role → 1-based attached slot
    product: ProductSpec = field(default_factory=ProductSpec)
    material: MaterialSpec = field(default_factory=MaterialSpec)
    colour: ColourSpec = field(default_factory=ColourSpec)
    camera: CameraSpec = field(default_factory=CameraSpec)
    scene: SceneSpec = field(default_factory=SceneSpec)
    editorial: EditorialSpec = field(default_factory=EditorialSpec)
    strict_in_place_recolor: bool = False
    lock_to_reference: bool = False
    use_swatch_for_fabric: bool = False
    swatch_texture_only: bool = False
    catalog_framing_contract: str = ""
    output_style: str = ""
    notes: str = ""

    # ---- derived ----------------------------------------------------- #
    @property
    def in_place_recolor(self) -> bool:
        return bool(
            self.strict_in_place_recolor
            and self.camera.preserve_from_base
            and (self.scene.mode == "packshot" or self.scene.keep_source_scene)
        )

    @property
    def reference_locked(self) -> bool:
        return bool(self.lock_to_reference and "extra_reference_1" in self.slots)

    def slot(self, role: str) -> Optional[int]:
        return self.slots.get(role)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
