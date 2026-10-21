"""Prompt compiler — ONE place that turns a PromptSpec into the text an
engine receives.

    PromptSpec  (spec.py)        what we want: product, material, colour,
                                 camera, scene, attached reference roles
    sections    (sections.py)    one function per paragraph, in prose
    compile()   (compile.py)     fixed section order per mode → str
    product_spec / freeform_spec (from_request.py)
                                 GenerationRequest / picker ids → PromptSpec

Phase 2a (2026-10): the compiler reproduces the previous wording byte for
byte (tests/test_prompt_compiler_parity.py proves it against a frozen copy
of the old builders). Phase 2b changes the wording and the order here, in
one place, with the goldens showing the diff.
"""
from app.core.prompt.compile import compile_prompt
from app.core.prompt.from_request import freeform_spec, product_spec
from app.core.prompt.spec import (
    CameraSpec,
    ColourSpec,
    EditorialSpec,
    MaterialSpec,
    ProductSpec,
    PromptSpec,
    SceneSpec,
    hex_to_rgb,
    is_dark_hex,
    relative_luminance,
)

__all__ = [
    "CameraSpec", "ColourSpec", "EditorialSpec", "MaterialSpec", "ProductSpec",
    "PromptSpec", "SceneSpec", "compile_prompt", "freeform_spec", "product_spec",
    "hex_to_rgb", "is_dark_hex", "relative_luminance",
]
