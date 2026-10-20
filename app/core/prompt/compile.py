"""compile_prompt(spec) → str. The section ORDER lives here and nowhere else.

Two orders today (phase 2a reproduces the old builders): the product
prompt and the freeform/editorial prompt. Phase 2b replaces both with one
order (task → keep-exactly → camera → backdrop/scene → material + colour →
reference roles → output) and measures the effect with the eval matrix.
"""
from __future__ import annotations

from collections.abc import Callable

from app.core.prompt import sections as S
from app.core.prompt.spec import PromptSpec

Section = Callable[[PromptSpec], list[str]]

PRODUCT_ORDER: list[Section] = [
    S.task,
    S.bed_frame_and_size,
    S.upholstery,
    S.bedding,
    S.legs,
    S.material_macro,
    S.colour_authority,
    S.material_angles,
    S.material_behavior,
    S.material_application,
    S.view_consistency,
    S.reference_lock,
    S.camera,
    S.catalog_contract,
    S.shadow,
    S.scene,
    S.preserve,
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
