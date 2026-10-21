"""compile_prompt(spec) → str. The section ORDER lives here and nowhere else.

Product order (phase 2b): what the product is and what must not change,
then the camera, then the backdrop or scene, then the material and colour,
then what every other attached image is for, then output. The framing
instruction therefore sits in the first fifth of the prompt instead of past
the middle, and nothing after it re-describes a viewpoint.
"""
from __future__ import annotations

from collections.abc import Callable

from app.core.prompt import sections as S
from app.core.prompt.spec import PromptSpec

Section = Callable[[PromptSpec], list[str]]

PRODUCT_ORDER: list[Section] = [
    S.task,
    S.product_identity,
    S.keep_exactly,
    S.reference_lock,
    S.camera,
    S.catalog_contract,
    S.shadow,
    S.scene,
    S.view_consistency,
    S.upholstery,
    S.bedding,
    S.colour_authority,
    S.material_macro,
    S.material_angles,
    S.material_behavior,
    S.material_application,
    S.moodboards,
    S.output_style,
    S.negatives,
    S.notes,
]

FREEFORM_ORDER: list[Section] = [
    S.ed_task,
    S.ed_references,
    S.ed_brief,
    S.ed_direction,
    S.ed_output,
]


def compile_prompt(spec: PromptSpec) -> str:
    order = FREEFORM_ORDER if spec.mode == "freeform" else PRODUCT_ORDER
    lines: list[str] = []
    for section in order:
        lines.extend(section(spec))
    return "\n".join(lines)


def section_names(spec: PromptSpec) -> list[str]:
    """Which sections contribute text for this spec — handy in traces."""
    order = FREEFORM_ORDER if spec.mode == "freeform" else PRODUCT_ORDER
    return [fn.__name__ for fn in order if fn(spec)]
