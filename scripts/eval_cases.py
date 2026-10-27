"""The fixed evaluation matrix shared by the golden-prompt tests and the live
eval runner.

One place defines WHICH requests we care about; two consumers use it:

  * tests/test_golden_prompts.py — snapshots the exact prompt text, the
    attached reference list and the system instruction for every case and
    engine. Any change to the wording is a deliberate golden update.
  * scripts/eval_matrix.py — sends the same requests to a real engine and
    stores the renders so scripts/eval_report.py can measure them.

The matrix is deliberately small and orthogonal:

  product  : bed + cremona/taupe (full curated reference set, hex)
             sofa + boucle/greige (single macro reference, hex)
  mode     : catalog (profile ivory, as the wizard posts it)
             lifestyle (env scandi, every camera field explicit)
  shot     : hero / close_up / detail_fabric
  engine   : gemini (schema cap) / openai (16-ref cap, no system instruction)

Plus one "ui-default" case that mirrors byte-for-byte what the wizard posts
today in catalog mode (only `yaw`, no shot), and one editorial brief.

Nothing here imports pytest, so the module is importable from scripts.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_V2 = REPO_ROOT / "app-v2"
for p in (REPO_ROOT, APP_V2):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.core.generator import (  # noqa: E402
    GenerationRequest,
    _build_prompt_text,
    _load_image,
    _load_reference_plan,
    load_freeform_reference_plan,
    slot_numbers,
)
from app.core.schema_loader import schema  # noqa: E402
from studio.mappings import _compose_bedding_description  # noqa: E402
from studio.openai_images import OPENAI_MODELS  # noqa: E402
from studio.request_builder import (  # noqa: E402
    _build_freeform_request,
    _build_generation_request,
)

from app.core.model_registry import registry  # noqa: E402

GEMINI_MODEL = registry.default_for("studio")   # the route default (models.json)
# The OpenAI-direct engine (the Lab itself now runs on OpenRouter): first
# active entry in models.json, i.e. GPT Image 2.5 Flare.
OPENAI_MODEL = registry.by_engine("openai", include_deprecated=False)[0].id

ENGINES = {
    "gemini": GEMINI_MODEL,
    "openai": OPENAI_MODEL,
}

PRODUCTS = {
    # kind: (material, colour id, size)
    "bed": ("cremona", "taupe", "160"),
    "sofa": ("boucle", "greige", "3"),
}
MODES = ("catalog", "lifestyle")
SHOTS = ("hero", "close_up", "detail_fabric")

EDITORIAL_BRIEF = (
    "Przytulna sypialnia o świcie, łóżko tapicerowane przy oknie, "
    "poranna mgła za szybą."
)

# The bedding the wizard composes for a bed by default (hotel / linen / minimal).
_DEFAULT_BEDDING = dict(
    bedding="linen_white", bedding_custom="", throw="none",
    tidy="hotel", density="minimal", accents_csv="", bed_note="",
)


@dataclass(frozen=True)
class Case:
    id: str
    engine: str                       # "gemini" | "openai"
    kind: str = ""                    # "bed" | "sofa" | "" for editorial
    mode: str = ""                    # "catalog" | "lifestyle" | "editorial"
    shot: str = ""                    # hero | close_up | detail_fabric | "" (ui default)
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def model(self) -> str:
        return ENGINES[self.engine]

    @property
    def freeform(self) -> bool:
        return self.mode == "editorial"


def _product_cases() -> list[Case]:
    cases: list[Case] = []
    for kind in PRODUCTS:
        for mode in MODES:
            for shot in SHOTS:
                for engine in ENGINES:
                    cases.append(Case(
                        id=f"{kind}-{mode}-{shot}-{engine}",
                        engine=engine, kind=kind, mode=mode, shot=shot,
                    ))
    # What the wizard actually posts in catalog mode today: only `yaw`.
    for engine in ENGINES:
        cases.append(Case(
            id=f"bed-catalog-ui_default-{engine}",
            engine=engine, kind="bed", mode="catalog", shot="",
            note="mirrors a pre-phase-4 client's catalog POST: only yaw, every camera field empty",
            extra=dict(lens="", dof="", height="", shot=""),
        ))
    for engine in ENGINES:
        cases.append(Case(
            id=f"editorial-bedroom-{engine}",
            engine=engine, mode="editorial",
        ))
    return cases


CASES: list[Case] = _product_cases()
CASE_BY_ID = {c.id: c for c in CASES}


# --------------------------------------------------------------------------
# Request construction — mirrors routes_generate.api_generate's call into
# _build_generation_request, with the same Form defaults.
# --------------------------------------------------------------------------
def build_request(case: Case, base_image: Optional[Path]) -> GenerationRequest:
    if case.freeform:
        return _build_freeform_request(
            api_key="eval-key", text=EDITORIAL_BRIEF,
            style="magazine_cover", env="scandi", tod="morning_cool",
            lens="50mm_natural", height="eye", color="taupe", mat="cremona",
            model=case.model, aspect="4:3", res="1K", seed="",
            max_refs=(OPENAI_MODELS[case.model]["max_refs"]
                      if case.engine == "openai" else None),
        )

    if base_image is None:
        raise ValueError(f"case {case.id} needs a base image")
    mat, color, size = PRODUCTS[case.kind]
    catalog = case.mode == "catalog"

    # Route Form defaults (routes_generate.api_generate).
    kwargs: dict[str, Any] = dict(
        api_key="eval-key", kind=case.kind,
        color=color, color_custom="",
        mat=mat, mat_notes="",
        size=size, legs="keep",
        cam="studio", lens="50mm_natural", tod="noon_neutral", shadow="soft_diffuse",
        shot=case.shot, yaw="34_left", height="", dof="", detail_region="",
        env="", env_note="", env_mode="",
        model=case.model, aspect="4:3", res="1K", seed="",
        base_image_path=base_image, scene_image_path=None,
        extra_reference_paths=[], lock_to_reference=False,
        preserve_camera_from_base=False,
        bedding_description=(
            _compose_bedding_description(**_DEFAULT_BEDDING) if case.kind == "bed" else ""
        ),
        catalog=catalog, catalog_profile="ivory" if catalog else "",
    )
    if catalog:
        # Phase 4: the wizard posts the camera it seeded when the locked
        # backdrop was picked (85 mm, f/8, eye level); the light is locked.
        kwargs.update(background="ivory", lens="85mm_product", dof="deep", height="eye")
    else:
        # Lifestyle: the wizard posts every camera field plus its scene.
        kwargs.update(background="scandi", env="scandi", env_mode="reference",
                      height="eye", dof="standard")
    kwargs.update(case.extra)
    return _build_generation_request(**kwargs)


# --------------------------------------------------------------------------
# Engine mirror — what each engine actually sends, computed WITHOUT the
# network call. Keep in sync with generator.generate() and
# openai_images.generate_product_openai().
# --------------------------------------------------------------------------
@dataclass
class Rendered:
    prompt: str
    system_instruction: str
    references: list[tuple[str, str]]   # (role, source label)
    max_refs: int
    plan: list[tuple[str, Any, Any]] = field(default_factory=list)   # (role, source, PIL image)


def _label(source: Any, base_image: Optional[Path]) -> str:
    text = str(source)
    if text.startswith("color-patch:"):
        return text
    if base_image is not None and Path(text) == Path(base_image):
        return "<base-image>"
    return Path(text).name


def render(case: Case, req: GenerationRequest, base_image: Optional[Path]) -> Rendered:
    """The cap and the system instruction follow `req.model_id` (which the
    live runner may override), the engine follows the registry. OpenRouter
    runs are treated like Gemini: same prompt, same system instruction
    (prepended by the runner, since the Images API has no system field)."""
    engine = registry.engine_of(req.model_id)
    if engine == "openai":
        max_refs = registry.max_refs(req.model_id, OPENAI_MODELS.get(req.model_id, {}).get("max_refs", 16))
        system_instruction = ""           # no system field; persona leads the prompt (below)
    else:
        max_refs = registry.max_refs(req.model_id, schema.max_refs_for_model(req.model_id))
        system_instruction = req.system_instruction or schema.system_instruction_default

    if case.freeform:
        loaded = load_freeform_reference_plan(req, max_refs)
        refs = [(slot.role, _label(slot.source, None)) for slot, _img in loaded]
        prompt = _build_prompt_text(req)   # freeform text is the prompt
        plan = [(slot.role, slot.source, img) for slot, img in loaded]
        return Rendered(prompt, system_instruction, refs, max_refs, plan)

    base_img = _load_image(req.base_product_image)
    assert base_img is not None, "base image unreadable"
    loaded = _load_reference_plan(req, base_img, max_refs)
    slots = slot_numbers([slot for slot, _img in loaded])
    prompt = _build_prompt_text(req, slots)
    if engine == "openai":
        persona = (req.system_instruction or schema.system_instruction_default).strip()
        if persona:
            prompt = f"{persona}\n\n{prompt}"
            system_instruction = "(no system field — the persona above is the first paragraph of the prompt)"
    refs = [(slot.role, _label(slot.source, base_image)) for slot, _img in loaded]
    plan = [(slot.role, slot.source, img) for slot, img in loaded]
    return Rendered(prompt, system_instruction, refs, max_refs, plan)


def prompt_stats(prompt: str) -> dict[str, Any]:
    """Cheap shape metrics. Where the framing instruction sits matters for
    these models; we record it so a refactor can prove it moved."""
    n = max(len(prompt), 1)

    def offset(marker: str) -> int:
        i = prompt.find(marker)
        return -1 if i < 0 else round(100 * i / n)

    return {
        "chars": len(prompt),
        "camera_offset_pct": offset("\nCAMERA"),
        "preserve_offset_pct": offset("\nPRESERVE"),
        "scene_offset_pct": offset("\nSCENE"),
        "negative_offset_pct": offset("\nNEGATIVE"),
    }


def golden_text(case: Case, req: GenerationRequest, rendered: Rendered) -> str:
    """Deterministic snapshot of everything that crosses the wire."""
    stats = prompt_stats(rendered.prompt)
    lines = [
        f"# golden prompt — case: {case.id}",
        f"# engine: {case.engine} | model: {case.model} | max_refs: {rendered.max_refs}",
        f"# kind={case.kind or '-'} mode={case.mode} shot={case.shot or '-'}"
        f" shot_type={req.shot_type} catalog_profile={'ivory' if case.mode == 'catalog' else '-'}",
        f"# colour={req.upholstery_hex or '-'} material_id={req.material_id or '-'}"
        f" aspect={req.aspect_ratio} res={req.resolution}",
        "# stats: " + " ".join(f"{k}={v}" for k, v in stats.items()),
    ]
    if case.note:
        lines.append(f"# note: {case.note}")
    lines.append("")
    lines.append(f"REFERENCES ({len(rendered.references)}):")
    for i, (role, label) in enumerate(rendered.references, start=1):
        lines.append(f"  {i}. {role:<24} {label}")
    lines.append("")
    lines.append("SYSTEM INSTRUCTION:")
    lines.append(rendered.system_instruction.strip() or "(none)")
    lines.append("")
    lines.append(f"PROMPT ({len(rendered.prompt)} chars):")
    lines.append(rendered.prompt.rstrip("\n"))
    return "\n".join(lines) + "\n"
