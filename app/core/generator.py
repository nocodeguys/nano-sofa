"""
generator.py — Assembles prompts from form state and calls the Gemini API.

Handles:
- Alpha-channel flattening (base_image_has_alpha flag)
- Reference slot assembly in declared order
- Exponential backoff retry for known 30–45% peak-hour failure rates
- Thought-signature extraction for multi-turn sessions
- Cost recording after each call
"""

from __future__ import annotations

import io
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from PIL import Image, PngImagePlugin

from app.core.cost_tracker import (
    GenerationRecord,
    estimate_cost,
    new_generation_id,
    record_generation,
)
from app.core.leg_browser import leg_browser
from app.core.generation_trace import build_generation_trace, write_generation_trace
from app.core.schema_loader import schema
from app.core.prompt import compile_prompt, product_spec
from app.core.prompt import sections as _sections
from app.core.prompt.spec import hex_to_rgb, is_dark_hex, relative_luminance  # noqa: F401

logger = logging.getLogger(__name__)

_OUTPUTS_DIR = Path(__file__).resolve().parents[1] / "outputs"
_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Retry configuration for known peak-hour failure rates
_MAX_RETRIES = 4
_BACKOFF_BASE_SECONDS = 2.0
_BACKOFF_MAX_SECONDS = 30.0

# Per-attempt request timeout (milliseconds). Bounds a hung Gemini connection
# so a single call can't occupy a worker thread indefinitely (the prior client
# had no deadline at all). Generous by default so legitimate slow 4K/Pro
# renders aren't cut off; overridable via env for slow links.
_REQUEST_TIMEOUT_MS = int(os.environ.get("GEMINI_TIMEOUT_MS", "120000"))

# 18% sRGB neutral grey (#7F7F7F) — matches legs/STANDARDS.md so flattened
# base products and leg-library renders share the same background value.
_ALPHA_FLATTEN_GREY = (127, 127, 127)


@dataclass
class GenerationRequest:
    """All parameters needed for a single generation call."""

    # Model
    model_id: str

    # Reference images (paths or PIL Images)
    base_product_image: Any   # PIL.Image or path string
    leg_reference_image: Optional[Any] = None   # PIL.Image or path string
    scene_reference_image: Optional[Any] = None
    swatch_reference_image: Optional[Any] = None
    material_left_reference_image: Optional[Any] = None
    material_right_reference_image: Optional[Any] = None
    material_behavior_reference_image: Optional[Any] = None
    material_application_reference_image: Optional[Any] = None

    # Extra moodboard-style references uploaded by the user in the UI's
    # "Referencje" section. Unlike the named slots above, these don't have a
    # specific prompt role — they're appended to the multimodal call so the
    # model can pick up style/material/lighting cues. Capped at runtime to
    # whatever the model's max_refs allows after the named slots are counted.
    extra_reference_images: list = field(default_factory=list)

    # Product
    product_type: str = "sofa"   # "sofa" | "bed"
    sofa_configuration: str = "3-seater"   # also used for bed sizes when product_type == "bed"
    frame_style: Optional[str] = None      # bed-only: platform, panel, sleigh, etc.
    leg_count: int = 4   # sofa default 4. bed default should be set by caller (0 for platform/divan)
    preserve_list: list[str] = field(default_factory=list)

    # Variant
    upholstery_color: str = "sage green"
    upholstery_material: str = "bouclé"
    texture_notes: str = ""
    base_image_has_alpha: bool = False

    # Structured identity of the chosen colour/material (catalog ids). The
    # text fields above are what the prompt says; these are what the render
    # is tagged with (PNG tEXt, trace, cost DB) so a file can still be matched
    # to a catalog entry after the prompt wording has been edited.
    color_id: str = ""
    material_id: str = ""
    fabric_code: str = ""
    # Exact target colour as #RRGGBB. When set, a flat colour patch is
    # attached as its own reference slot (COLOUR AUTHORITY) and deep shades
    # get a dedicated exposure clause — text alone drifts on dark colours.
    upholstery_hex: str = ""
    # Engine-specific quality tier (OpenAI Images API `quality`: low … max).
    # Ignored by the Gemini path.
    engine_quality: str = ""

    # Freeform (editorial) mode: when non-empty, this text IS the whole prompt
    # — the variant prompt assembly is skipped entirely, and the base product
    # image becomes optional (pure text-to-image, plus optional moodboard refs
    # via extra_reference_images). The caller composes the text; see
    # studio/request_builder._build_freeform_request.
    freeform_prompt: str = ""

    # Legs
    leg_id: Optional[str] = None
    leg_explicit_descriptor: str = ""
    leg_instruction: str = ""

    # Camera
    camera_angle: str = "front-34-left"
    angle_degrees_from_left: int = 35
    shadow_direction: str = "4 o-clock"
    focal_length_mm: int = 50
    aperture: str = "f/4.5"
    framing: str = "full product visible with breathing room above and below"

    # Shot type — the framing intent. Detail variants change two things in the
    # emitted prompt: the CAMERA block drops the yaw line (a yaw at macro
    # distance is nonsensical and conflicts with the crop), and the SCENE
    # block emits a short out-of-focus background description instead of the
    # full cyclorama spec (which describes a hero packshot and overrides
    # the detail crop instruction — the original failure the user reported).
    #
    # Values:
    #   wide / hero / three_quarter / cropped  → standard framing
    #   detail_fabric                          → extreme macro on upholstery surface
    #   detail_corner                          → tight crop on a single region
    shot_type: str = "hero"
    # Optional region phrase woven into the framing string for detail shots
    # (e.g. "the upholstery fabric weave pattern", "the corner where the arm
    # meets the backrest"). Empty for non-detail shot_types.
    detail_region_phrase: str = ""

    # Scene — structured fields that feed the SCENE block as a narrative
    # paragraph instead of buried name=value notes. When env_mode is empty
    # the SCENE block falls back to the legacy single-line behavior so
    # callers that haven't migrated yet keep working.
    lens_descriptor: str = ""       # e.g. "85 mm short telephoto, mild background compression"
    tod_description: str = ""       # e.g. "midday neutral daylight, ~5500 K, overhead light"
    shadow_description: str = ""    # full sentence describing shadow quality
    env_mode: str = ""              # "" | "packshot" | "lifestyle"
    env_description: str = ""       # full English scene description

    # When True, the prompt emits a strong "same room, different angle"
    # paragraph above CAMERA. Used by the lifestyle pair pass in
    # /api/generate-photoshoot, where the scene_reference_image is the
    # anchor lifestyle render and the model must preserve every room
    # detail while accepting a new product angle from the base image.
    view_consistency: bool = False

    # The scene reference shows this same product in another upholstery
    # colour (variant sets reuse the anchor render as the room reference).
    # The prompt then names it as a room/lighting reference only and forbids
    # copying its upholstery colour.
    scene_contains_product: bool = False

    # When True, the prompt emits a "swatch reference" paragraph that tells
    # the model to copy ONLY the fabric color and texture from the swatch
    # reference image, not its geometry or shadows. Used by the packshot
    # batch pass to lock fabric appearance across N angle renders.
    use_swatch_for_fabric: bool = False

    # Canonical material-library swatches describe microscopic construction
    # only. Their photographed colour must not override the colour selected in
    # the configurator. User/anchor swatches can keep the historical
    # colour+texture behaviour by leaving this False.
    swatch_texture_only: bool = False

    # When True, the CAMERA block emits "preserve angle/framing/pose from
    # the base image" instead of the wizard-configured camera_angle. Used
    # by the photoshoot session where every render's correct angle is
    # already encoded in that render's individual base image (the user's
    # source angle photo). Without this flag, every variant in a session
    # would be forced to the wizard's single cam preset — which is the
    # opposite of what a multi-angle photoshoot needs.
    preserve_camera_from_base: bool = False

    # When True, the prompt switches into "near-pixel-identical recolor of
    # slot 1" mode — only the upholstery color/material change, everything
    # else (camera, scene, background, framing, crop) is preserved verbatim.
    # This is the Fotosesja packshot-pass behavior; it should NOT be used
    # when the caller wants to swap the background via env_mode. The wizard
    # "Zachowaj kąt z bazowego zdjęcia" toggle sets preserve_camera_from_base
    # but NOT this flag — so the wizard's chosen env still applies.
    strict_in_place_recolor: bool = False

    # When True, the recolor keeps the SOURCE image's own background/scene
    # verbatim: the SCENE backdrop block is suppressed and the prompt is told to
    # preserve slot 1's exact environment. Used by Fotosesja v2 (recolor a user's
    # existing photo, change only colour/material). Lets the strict-recolor mode
    # activate independent of env_mode — see in_place_recolor in _build_prompt_text.
    keep_source_scene: bool = False

    # When True AND extra_reference_images is non-empty, the prompt names the
    # first extra reference as the authoritative source of CAMERA, LIGHTING,
    # SHADOW, and SCENE/BACKDROP appearance — and suppresses the wizard's
    # camera_angle / framing / lens / env description / shadow direction so
    # they don't fight the reference. Variant attributes (color, material,
    # legs) still come from the wizard: this is "apply my new color in the
    # look of this reference photo," not "ignore everything and clone the
    # reference." Toggled by the section-09 "Użyj referencji jako wzorca"
    # checkbox in the UI.
    lock_to_reference: bool = False

    # Quantified framing contract emitted by catalog mode — subject scale,
    # horizontal centring and floor-contact height stated as percentages of
    # the frame. The qualitative `framing` string ("breathing room above and
    # below") is read differently for a low platform bed than for a tall
    # continental one, which is what makes a product grid look like eight
    # separate shoots. Numbers remove the interpretation. Emitted verbatim in
    # its own block and deliberately NOT suppressed by lock_to_reference: the
    # anchor was rendered under the same contract, so the two agree.
    catalog_framing_contract: str = ""

    # Output
    aspect_ratio: str = "4:3"
    resolution: str = "1K"
    output_style: str = "e-commerce hero photography, photorealistic, neutral color grading"

    # System + negative
    system_instruction: str = ""
    negative_list: list[str] = field(default_factory=list)

    # Notes
    notes: str = ""

    # Bed-only styling block — composed by server.py from the wizard's section
    # 10 (Pościel i styling) selections. When non-empty AND product_type == "bed",
    # the prompt emits a dedicated BEDDING block telling Gemini exactly what
    # textiles are on the bed, how tidy they should be, and how many extra
    # styling items belong in the frame. Empty for sofas and for beds where
    # the user left every field at its default with "bez pościeli" selected.
    bedding_description: str = ""

    # API key — per-user, supplied via the UI. Falls back to GEMINI_API_KEY
    # environment variable only when this field is empty.
    api_key: str = ""

    # Multi-turn
    # prior_history is an opaque list of google.genai.types.Content objects from
    # earlier turns in this chain (alternating user/model). On each new turn,
    # generate() prepends them to the contents list so the model sees the full
    # conversation including thought_signature parts on prior model turns —
    # the documented mitigation for identity drift in multi-turn edits.
    turn_number: int = 1
    prior_history: list[Any] = field(default_factory=list)


@dataclass
class GenerationResult:
    """Result of a single generation call."""
    success: bool
    generation_id: str
    output_path: Optional[Path]
    output_image: Optional[Image.Image]
    # next_history is the prior_history extended with the user Content sent on
    # this call and the model Content received in response (which carries any
    # thought_signature parts). Pass it back as prior_history on the next turn
    # to maintain context.
    next_history: list[Any]
    actual_cost: float
    attempts: int
    error_message: Optional[str]
    model_id: str
    resolution: str
    # Structured error metadata — populated only on failure. `error_code` is a
    # stable machine string the frontend keys off (see _ERROR_CATALOG);
    # `error_detail` is the raw technical message (EN, for logs / debugging);
    # `retryable` tells the UI whether a "try again" is worth offering;
    # `http_status` is the status the API layer should return.
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    retryable: bool = False
    http_status: int = 500
    elapsed_ms: Optional[int] = None   # measured wall-clock of this call


@dataclass
class ErrorInfo:
    """Classified, user-facing error. Bilingual: PL is primary (the UI), EN is
    the secondary detail line."""
    error_code: str
    message_pl: str
    message_en: str
    retryable: bool
    http_status: int


# code → (http_status, retryable, PL message, EN message). Single source of
# truth for how every failure is explained to the user. Keep messages
# actionable: tell the user what to do, not just what broke.
_ERROR_CATALOG: dict[str, tuple[int, bool, str, str]] = {
    "MODEL_OVERLOADED": (
        503, True,
        "Model Gemini jest chwilowo przeciążony. Spróbuj ponownie za chwilę.",
        "Gemini model temporarily overloaded (503 UNAVAILABLE).",
    ),
    "RATE_LIMITED": (
        429, True,
        "Przekroczono limit zapytań do API Gemini. Odczekaj chwilę i spróbuj ponownie "
        "(lub sprawdź limity/rozliczenia swojego klucza).",
        "Rate / quota limit hit (429 RESOURCE_EXHAUSTED).",
    ),
    "AUTH_INVALID_KEY": (
        401, False,
        "Klucz API jest nieprawidłowy lub nie ma uprawnień do tego modelu. "
        "Sprawdź klucz Gemini w polu na górze strony.",
        "API key invalid or lacks permission (401/403).",
    ),
    "INVALID_REQUEST": (
        400, False,
        "Żądanie zostało odrzucone — nieprawidłowe parametry generowania. "
        "Zmień ustawienia (model, proporcje, rozdzielczość) i spróbuj ponownie.",
        "Request rejected by the API (400 INVALID_ARGUMENT).",
    ),
    "BILLING_REQUIRED": (
        402, False,
        "Ten model (np. Veo — wideo) wymaga włączonego rozliczenia (paid tier) "
        "na projekcie Google Cloud powiązanym z kluczem API. Darmowy tier nie "
        "obejmuje Veo — włącz billing w Google Cloud Console (Billing) dla tego "
        "projektu i spróbuj ponownie.",
        "Model requires a billed (paid-tier) Google Cloud project.",
    ),
    "UPSTREAM_ERROR": (
        502, True,
        "Błąd po stronie serwera Gemini. Spróbuj ponownie za chwilę.",
        "Upstream Gemini server error (500/502/504).",
    ),
    "NETWORK_TIMEOUT": (
        504, True,
        "Brak połączenia z API lub przekroczono czas oczekiwania. "
        "Sprawdź internet i spróbuj ponownie.",
        "Network timeout / connection error.",
    ),
    "SAFETY_NO_IMAGE": (
        422, False,
        "Model nie zwrócił obrazu — prawdopodobnie blokada bezpieczeństwa lub treści. "
        "Zmień zdjęcie bazowe, prompt lub referencje i spróbuj ponownie.",
        "No image returned (likely a safety / recitation block).",
    ),
    "MISSING_API_KEY": (
        400, False,
        "Brak klucza API. Wklej swój klucz Gemini API w polu na górze strony "
        "(sekcja \"Klucz API\") i spróbuj ponownie.",
        "No API key provided.",
    ),
    "BAD_INPUT_IMAGE": (
        400, False,
        "Nie udało się wczytać zdjęcia bazowego. Wgraj poprawny plik JPG lub PNG.",
        "Could not load base product image.",
    ),
    "SERVER_MISCONFIG": (
        500, False,
        "Błąd konfiguracji serwera. Skontaktuj się z administratorem.",
        "Server misconfigured (google-genai not installed).",
    ),
    "UNKNOWN": (
        500, True,
        "Nieznany błąd generowania. Spróbuj ponownie.",
        "Unknown generation error.",
    ),
}


def _err(code: str) -> ErrorInfo:
    http, retry, pl, en = _ERROR_CATALOG[code]
    return ErrorInfo(error_code=code, message_pl=pl, message_en=en,
                     retryable=retry, http_status=http)


def classify_exception(exc: Exception) -> ErrorInfo:
    """
    Map a raw exception from the Gemini call to a stable ErrorInfo. The genai
    SDK raises google.genai.errors.APIError subclasses carrying an HTTP `.code`
    (int) and a `.status` string (e.g. "UNAVAILABLE", "RESOURCE_EXHAUSTED").
    Everything else (httpx/socket errors, timeouts) is treated as network or,
    failing that, UNKNOWN.
    """
    try:
        from google.genai import errors as genai_errors
        if isinstance(exc, genai_errors.APIError):
            code = getattr(exc, "code", None)
            status = (getattr(exc, "status", "") or "").upper()
            if code == 429 or status == "RESOURCE_EXHAUSTED":
                return _err("RATE_LIMITED")
            if code == 503 or status == "UNAVAILABLE":
                return _err("MODEL_OVERLOADED")
            if code in (401, 403) or status in ("UNAUTHENTICATED", "PERMISSION_DENIED"):
                return _err("AUTH_INVALID_KEY")
            if code == 400 or status in ("INVALID_ARGUMENT", "FAILED_PRECONDITION"):
                # Google returns 400 INVALID_ARGUMENT for several distinct causes;
                # disambiguate on the message so the user gets an actionable error.
                msg = str(getattr(exc, "message", "") or exc).lower()
                if any(k in msg for k in ("billed users", "billing", "paid tier", "paid-tier")):
                    return _err("BILLING_REQUIRED")
                if any(k in msg for k in ("api key not valid", "api_key_invalid", "api key expired")):
                    return _err("AUTH_INVALID_KEY")
                return _err("INVALID_REQUEST")
            # any other API error (incl. 500/502/504/INTERNAL/DEADLINE) → upstream
            return _err("UPSTREAM_ERROR")
    except Exception:
        pass
    # Non-API: network / timeout heuristics (httpx raises ReadTimeout,
    # ConnectError, etc. — not subclasses of the builtin TimeoutError).
    name = type(exc).__name__.lower()
    if isinstance(exc, (TimeoutError, ConnectionError)) or "timeout" in name or "connect" in name:
        return _err("NETWORK_TIMEOUT")
    return _err("UNKNOWN")


def _flatten_alpha(img: Image.Image) -> Image.Image:
    """
    Flatten any alpha channel to 18% neutral grey.
    Mitigates background-bleed failure mode when transparent-background PNGs
    are passed as reference images.
    """
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        background = Image.new("RGB", img.size, _ALPHA_FLATTEN_GREY)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[3])
        logger.info("Alpha channel detected and flattened to 18%% grey (%s px)", img.size)
        return background
    return img.convert("RGB") if img.mode != "RGB" else img


def _load_image(source: Any) -> Optional[Image.Image]:
    """Load a PIL Image from a path string, Path, or return as-is if already PIL."""
    if source is None:
        return None
    if isinstance(source, Image.Image):
        return source
    try:
        return Image.open(str(source))
    except Exception as exc:
        logger.warning("Could not load image from %r: %s", source, exc)
        return None


@dataclass
class ReferenceSlot:
    """One planned reference: its prompt role, a trace-friendly source label,
    and an optional preloaded image (synthetic references such as the colour
    patch never exist on disk)."""

    role: str
    source: Any
    image: Optional[Image.Image] = None


_COLOR_PATCH_SIZE = 512
# Relative luminance below which a shade is treated as deep/near-black and
# gets the DEEP-SHADE EXPOSURE clause. Forest green (#2E3B2C), chocolate
# (#4E3E2F) and black qualify; graphite (#656F70) and olive (#6A7763) do not.
_DARK_LUMINANCE = 0.06


# Colour helpers live in app.core.prompt.spec; re-exported for old callers.
_hex_to_rgb = hex_to_rgb


def _color_patch_image(hex_value: str) -> Optional[Image.Image]:
    rgb = _hex_to_rgb(hex_value)
    if rgb is None:
        return None
    return Image.new("RGB", (_COLOR_PATCH_SIZE, _COLOR_PATCH_SIZE), rgb)


def plan_reference_slots(
    req: GenerationRequest, max_refs: Optional[int] = None
) -> list[ReferenceSlot]:
    """Decide which references are attached and in what order.

    This is the ONE place that enforces the model's reference cap. Priority
    after the base product (always slot 1): leg, scene, then — when the caller
    locked the look to a moodboard — that moodboard; the material macro; the
    exact colour patch; the oblique / behaviour / application material views;
    the remaining moodboards. Anything past the cap is dropped here, with a
    warning, so the prompt and the trace only ever describe attached images.
    `max_refs` overrides the schema cap for engines the schema does not know
    (the OpenAI Images API in the Lab tab).
    """
    if max_refs is None:
        max_refs = schema.max_refs_for_model(req.model_id)
    wanted: list[ReferenceSlot] = [ReferenceSlot("base_product", req.base_product_image)]
    if req.leg_reference_image is not None:
        wanted.append(ReferenceSlot("leg", req.leg_reference_image))
    if req.scene_reference_image is not None:
        wanted.append(ReferenceSlot("scene", req.scene_reference_image))
    extras = list(req.extra_reference_images or [])
    next_extra_index = 1
    if req.lock_to_reference and extras:
        wanted.append(ReferenceSlot("extra_reference_1", extras.pop(0)))
        next_extra_index = 2
    if req.swatch_reference_image is not None:
        wanted.append(ReferenceSlot("material_macro", req.swatch_reference_image))
    patch = _color_patch_image(req.upholstery_hex) if req.upholstery_hex else None
    if patch is not None:
        wanted.append(
            ReferenceSlot("color_patch", f"color-patch:{req.upholstery_hex.strip().upper()}", patch)
        )
    for role, source in (
        ("material_left", req.material_left_reference_image),
        ("material_right", req.material_right_reference_image),
        ("material_behavior", req.material_behavior_reference_image),
        ("material_application", req.material_application_reference_image),
    ):
        if source is not None:
            wanted.append(ReferenceSlot(role, source))
    for offset, extra in enumerate(extras):
        wanted.append(ReferenceSlot(f"extra_reference_{next_extra_index + offset}", extra))

    kept = wanted[:max_refs]
    for dropped in wanted[max_refs:]:
        logger.warning(
            "Reference %s dropped: model %s allows max %d refs",
            dropped.role, req.model_id, max_refs,
        )
    return kept


def plan_freeform_reference_slots(
    req: GenerationRequest, max_refs: Optional[int] = None
) -> list[ReferenceSlot]:
    """Reference plan for editorial / text-to-image requests (no base product).

    Material authority first — the macro swatch, the exact colour patch, the
    oblique views, the light-response and in-use photographs — then the
    moodboards. `max_refs` overrides the schema cap for engines the schema
    does not know (OpenRouter / OpenAI models). The cap is applied here and
    nowhere else, so a prompt composed from this plan only ever names images
    that are actually attached.
    """
    cap = max_refs if max_refs is not None else schema.max_refs_for_model(req.model_id)
    wanted: list[ReferenceSlot] = []
    if req.swatch_reference_image is not None:
        wanted.append(ReferenceSlot("material_macro", req.swatch_reference_image))
    patch = _color_patch_image(req.upholstery_hex) if req.upholstery_hex else None
    if patch is not None:
        wanted.append(
            ReferenceSlot("color_patch", f"color-patch:{req.upholstery_hex.strip().upper()}", patch)
        )
    for role, source in (
        ("material_left", req.material_left_reference_image),
        ("material_right", req.material_right_reference_image),
        ("material_behavior", req.material_behavior_reference_image),
        ("material_application", req.material_application_reference_image),
    ):
        if source is not None:
            wanted.append(ReferenceSlot(role, source))
    for index, extra in enumerate(req.extra_reference_images or [], start=1):
        wanted.append(ReferenceSlot(f"extra_reference_{index}", extra))

    kept = wanted[: max(0, cap)]
    for dropped in wanted[len(kept):]:
        logger.warning(
            "Freeform reference %s dropped: model %s allows max %d refs",
            dropped.role, req.model_id, cap,
        )
    return kept


def load_freeform_reference_plan(
    req: GenerationRequest, max_refs: Optional[int] = None
) -> list[tuple[ReferenceSlot, Image.Image]]:
    """Load the freeform plan. An unreadable reference is skipped (with a
    warning) and the slots after it move up — callers number slots from the
    returned list."""
    loaded: list[tuple[ReferenceSlot, Image.Image]] = []
    for slot in plan_freeform_reference_slots(req, max_refs):
        image = slot.image if slot.image is not None else _load_image(slot.source)
        if image is None:
            logger.warning(
                "Freeform reference %s could not be loaded (%s); skipping",
                slot.role, slot.source,
            )
            continue
        loaded.append((slot, image))
    return loaded


def slot_numbers(plan: list[ReferenceSlot]) -> dict[str, int]:
    """role → 1-based slot number for a planned/loaded reference list."""
    return {slot.role: index for index, slot in enumerate(plan, start=1)}


def _count_active_refs(req: GenerationRequest) -> int:
    if req.freeform_prompt and req.base_product_image is None:
        return len(plan_freeform_reference_slots(req))
    return len(plan_reference_slots(req))


def _load_reference_plan(
    req: GenerationRequest, base_img: Image.Image, max_refs: Optional[int] = None
) -> list[tuple[ReferenceSlot, Image.Image]]:
    """Load every planned reference. A reference that fails to load is
    skipped and the slots after it move up — the caller must number slots
    from the returned list, never from the request."""
    loaded: list[tuple[ReferenceSlot, Image.Image]] = []
    for slot in plan_reference_slots(req, max_refs):
        if slot.role == "base_product":
            loaded.append((slot, base_img))
            continue
        image = slot.image if slot.image is not None else _load_image(slot.source)
        if image is None:
            logger.warning(
                "Reference %s could not be loaded (%s); skipping", slot.role, slot.source
            )
            continue
        loaded.append((slot, image))
    return loaded


def _collect_reference_images(
    req: GenerationRequest, base_img: Image.Image
) -> list[Image.Image]:
    """Reference images in attached order (slot 1 = base product)."""
    return [image for _slot, image in _load_reference_plan(req, base_img)]


def _build_scene_block(
    req: GenerationRequest, product_noun: str, slots: Optional[dict[str, int]] = None
) -> str:
    """SCENE section only — kept for callers that want just that paragraph.
    The wording lives in app/core/prompt/sections.py."""
    if slots is None:
        slots = slot_numbers(plan_reference_slots(req))
    return _sections._scene_block(product_spec(req, slots))


def _build_prompt_text(
    req: GenerationRequest, slots: Optional[dict[str, int]] = None
) -> str:
    """
    The full prompt text for a request: GenerationRequest → PromptSpec →
    compile_prompt (app/core/prompt). `slots` maps reference roles to the
    1-based slot numbers that were ACTUALLY attached (see
    plan_reference_slots); generate() always passes the loaded list so the
    prompt never names a missing image.
    """
    # Freeform/editorial requests carry their complete prompt verbatim.
    if req.freeform_prompt:
        return req.freeform_prompt
    if slots is None:
        slots = slot_numbers(plan_reference_slots(req))
    return compile_prompt(product_spec(req, slots))


def _pil_to_part(img: Image.Image, gtypes) -> Any:
    """Convert a PIL image to a google.genai.types.Part with PNG bytes."""
    buf = io.BytesIO()
    rgb = img if img.mode == "RGB" else img.convert("RGB")
    rgb.save(buf, format="PNG")
    return gtypes.Part.from_bytes(data=buf.getvalue(), mime_type="image/png")


def _is_retryable_error(exc: Exception) -> bool:
    """Whether `exc` is transient and worth retrying. Delegates to the single
    classifier so the retry loop and the user-facing taxonomy never disagree:
    overload (503), rate limit (429), upstream 5xx, and network/timeout are
    retryable; deterministic client errors (400 invalid args, 401/403 auth) are
    not — retrying them just burns ~14s of backoff before the identical
    failure."""
    return classify_exception(exc).retryable


def _png_text_metadata(req: GenerationRequest, generation_id: str, ts: int) -> dict[str, str]:
    """tEXt entries embedded into every master PNG so the file is self-identifying.

    The filename only carries the first 8 hex chars of the generation_id; these
    chunks carry the FULL id plus the variant attributes, so a render can be
    traced back and reused as an anchor for a variant set without a DB round-trip
    (and survives being downloaded / re-imported). All values must be str — the
    PNG tEXt chunk format is text-only.
    """
    return {
        "nano_sofa_schema": "1",
        "nano_sofa_generation_id": generation_id,
        "nano_sofa_ts": str(ts),
        "nano_sofa_model": req.model_id or "",
        "nano_sofa_resolution": req.resolution or "",
        "nano_sofa_color": req.upholstery_color or "",
        "nano_sofa_material": req.upholstery_material or "",
        "nano_sofa_color_id": req.color_id or "",
        "nano_sofa_material_id": req.material_id or "",
        "nano_sofa_fabric_code": req.fabric_code or "",
        "nano_sofa_color_hex": req.upholstery_hex or "",
        "nano_sofa_leg_id": req.leg_id or "",
        "nano_sofa_camera_angle": req.camera_angle or "",
        "nano_sofa_prompt_summary": _build_prompt_summary(req),
    }


def generate(req: GenerationRequest) -> GenerationResult:
    """
    Main entry point. Calls the Gemini API with retry logic.
    Saves the output image to disk and records cost.
    """
    generation_id = new_generation_id()
    _t0 = time.monotonic()
    is_freeform = bool(req.freeform_prompt) and req.base_product_image is None
    slot_roles: list[tuple[str, Any]] = []

    if is_freeform:
        # Editorial text-to-image: no base product slot. The fabric's
        # reference set, the colour patch and the moodboards ride along,
        # capped to the model's limit by plan_freeform_reference_slots.
        loaded_freeform = load_freeform_reference_plan(req)
        ref_images = [image for _slot, image in loaded_freeform]
        slot_roles = [(slot.role, slot.source) for slot, _image in loaded_freeform]
    else:
        # -------------------------------------------------------------- #
        # Alpha-channel flattening
        # -------------------------------------------------------------- #
        base_img = _load_image(req.base_product_image)
        if base_img is None:
            return GenerationResult(
                success=False,
                generation_id=generation_id,
                output_path=None,
                output_image=None,
                next_history=list(req.prior_history),
                actual_cost=0.0,
                attempts=0,
                error_message=_ERROR_CATALOG["BAD_INPUT_IMAGE"][2],
                error_code="BAD_INPUT_IMAGE",
                error_detail="Could not load base product image.",
                retryable=False,
                http_status=400,
                model_id=req.model_id,
                resolution=req.resolution,
            )

        if req.base_image_has_alpha or base_img.mode in ("RGBA", "LA"):
            base_img = _flatten_alpha(base_img)
            logger.info("Base product image flattened from alpha (alpha bleed mitigation)")

        loaded = _load_reference_plan(req, base_img)
        ref_images = [image for _slot, image in loaded]
        slot_roles = [(slot.role, slot.source) for slot, _image in loaded]

    num_refs = len(ref_images)
    cost_est = estimate_cost(req.model_id, req.resolution, num_refs)
    slots = {role: index for index, (role, _source) in enumerate(slot_roles, start=1)}
    prompt_text = _build_prompt_text(req, slots)
    effective_system_instruction = (
        req.system_instruction or schema.system_instruction_default
    )
    generation_trace = build_generation_trace(
        req=req,
        generation_id=generation_id,
        prompt=prompt_text,
        effective_system_instruction=effective_system_instruction,
        reference_images=ref_images,
        freeform=is_freeform,
        reference_roles=slot_roles,
    )
    reference_log = ", ".join(
        f"{ref['slot']}:{ref['role']}={Path(ref['source']).name}"
        for ref in generation_trace["references"]
    )
    logger.info(
        "Generation setup id=%s setup=%s exact=%s refs=[%s]",
        generation_id,
        generation_trace["setup_fingerprint"][:12],
        generation_trace["exact_fingerprint"][:12],
        reference_log,
    )

    # Opt-in full-prompt dump. Only the one-line summary is logged otherwise,
    # which is useless when iterating on texture/scene wording — there was no
    # way to see what actually crossed the wire. Off by default so production
    # logs stay quiet; set NANO_SOFA_LOG_PROMPT=1 when tuning prompts.
    if os.environ.get("NANO_SOFA_LOG_PROMPT"):
        logger.info(
            "── PROMPT → Gemini (%d chars, %d refs) ──\n%s\n── END PROMPT ──",
            len(prompt_text), len(ref_images), prompt_text,
        )

    # ------------------------------------------------------------------ #
    # API call with exponential backoff
    # ------------------------------------------------------------------ #
    # Prefer the per-request key supplied via the UI; fall back to env only
    # for legacy / scripted use. Never log the key.
    api_key = (req.api_key or "").strip() or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return GenerationResult(
            success=False,
            generation_id=generation_id,
            output_path=None,
            output_image=None,
            next_history=list(req.prior_history),
            actual_cost=0.0,
            attempts=0,
            error_message=_ERROR_CATALOG["MISSING_API_KEY"][2],
            error_code="MISSING_API_KEY",
            error_detail="No API key provided.",
            retryable=False,
            http_status=400,
            model_id=req.model_id,
            resolution=req.resolution,
        )

    try:
        from google import genai
        from google.genai import types as gtypes
    except ImportError:
        return GenerationResult(
            success=False,
            generation_id=generation_id,
            output_path=None,
            output_image=None,
            next_history=list(req.prior_history),
            actual_cost=0.0,
            attempts=0,
            error_message=_ERROR_CATALOG["SERVER_MISCONFIG"][2],
            error_code="SERVER_MISCONFIG",
            error_detail="google-genai package not installed. Run: pip install google-genai",
            retryable=False,
            http_status=500,
            model_id=req.model_id,
            resolution=req.resolution,
        )

    client = genai.Client(
        api_key=api_key,
        http_options=gtypes.HttpOptions(timeout=_REQUEST_TIMEOUT_MS),
    )

    # Build the user-turn Content explicitly so we can preserve it in the
    # conversation history alongside the model's response (which carries
    # thought_signature parts on its parts).
    user_parts = [gtypes.Part.from_text(text=prompt_text)]
    for img in ref_images:
        user_parts.append(_pil_to_part(img, gtypes))
    user_content = gtypes.Content(role="user", parts=user_parts)

    contents = list(req.prior_history) + [user_content]

    # Build ImageConfig.
    # google-genai 2.0.0 renamed the resolution kwarg to `image_size`. The
    # accepted vocabulary is unchanged: "1K" / "2K" / "4K". Keeping
    # GenerationRequest.resolution as the public field name so callers don't
    # have to learn the SDK quirk.
    image_config_kwargs: dict[str, Any] = {"aspect_ratio": req.aspect_ratio}
    if schema.supports_resolution_param(req.model_id) and req.resolution != "1K":
        image_config_kwargs["image_size"] = req.resolution

    config = gtypes.GenerateContentConfig(
        system_instruction=effective_system_instruction,
        response_modalities=["IMAGE"],
        image_config=gtypes.ImageConfig(**image_config_kwargs),
    )

    last_error: str = ""
    last_exc: Optional[Exception] = None
    output_image: Optional[Image.Image] = None
    model_content: Optional[Any] = None
    attempts_made = 0

    for attempt in range(1, _MAX_RETRIES + 1):
        attempts_made = attempt
        try:
            logger.info(
                "Calling %s (attempt %d/%d, %d refs, history depth=%d)",
                req.model_id,
                attempt,
                _MAX_RETRIES,
                num_refs,
                len(req.prior_history),
            )
            response = client.models.generate_content(
                model=req.model_id,
                contents=contents,
                config=config,
            )

            model_content = response.candidates[0].content

            for part in model_content.parts:
                if part.inline_data and part.inline_data.data:
                    output_image = Image.open(io.BytesIO(part.inline_data.data))
                    break

            if output_image is None:
                last_error = "API returned a response but no image data was present."
                logger.warning("Attempt %d: no image in response — %s", attempt, last_error)
                if attempt < _MAX_RETRIES:
                    _sleep_backoff(attempt)
                continue

            # Success
            break

        except Exception as exc:
            last_error = str(exc)
            last_exc = exc
            retryable = _is_retryable_error(exc)
            logger.warning(
                "Attempt %d failed (%sretryable): %s",
                attempt, "" if retryable else "non-", last_error,
            )
            if retryable and attempt < _MAX_RETRIES:
                _sleep_backoff(attempt)
            else:
                # Non-retryable (bad key, invalid args, safety) — stop now
                # rather than waste the remaining attempts + backoff.
                break

    # ------------------------------------------------------------------ #
    # Persist output
    # ------------------------------------------------------------------ #
    output_path: Optional[Path] = None
    status = "failed"
    actual_cost = 0.0

    if output_image is not None:
        ts = int(time.time())
        filename = f"{ts}_{req.model_id.replace('.', '-')}_{generation_id[:8]}.png"
        output_path = _OUTPUTS_DIR / filename
        # This PNG is the lossless canonical master: it is what gets reused as a
        # pixel-lock reference for variant/photoshoot batches, so it must stay
        # lossless. optimize=True is a free, lossless size reduction. The
        # user-facing download (JPG/WebP) is derived from this master by the
        # server layer — never the other way round.
        #
        # Embed identity metadata as PNG tEXt chunks: the full generation_id +
        # variant attributes travel WITH the file, so it can be traced and
        # reused as a variant-set anchor (the filename only holds an 8-char id
        # prefix). tEXt is lossless and ignored by viewers.
        _pnginfo = PngImagePlugin.PngInfo()
        for _meta_k, _meta_v in _png_text_metadata(req, generation_id, ts).items():
            _pnginfo.add_text(_meta_k, _meta_v)
        output_image.save(str(output_path), format="PNG", optimize=True, pnginfo=_pnginfo)
        status = "success"
        actual_cost = cost_est.total_low  # use conservative (low) estimate as actual

    # Classify the failure (if any) into a stable, user-facing ErrorInfo. A
    # response with no image part is almost always a safety / recitation block;
    # otherwise classify the last raw exception.
    err_info: Optional[ErrorInfo] = None
    if output_image is None:
        if last_exc is not None:
            err_info = classify_exception(last_exc)
        else:
            err_info = _err("SAFETY_NO_IMAGE")

    elapsed_ms = int((time.monotonic() - _t0) * 1000)

    generation_trace["status"] = status
    generation_trace["result"] = {
        "output_path": str(output_path) if output_path else None,
        "actual_cost": actual_cost,
        "estimated_cost_low": cost_est.total_low,
        "estimated_cost_high": cost_est.total_high,
        "elapsed_ms": elapsed_ms,
        "attempts": attempts_made,
        "error": last_error if status == "failed" else None,
    }
    # Resolve from _OUTPUTS_DIR at call time: app-v2/studio/paths.py redirects
    # that directory during startup, and traces must follow the rendered files.
    trace_path = write_generation_trace(generation_trace, _OUTPUTS_DIR / "traces")
    logger.info("Generation trace saved: %s", trace_path)

    # Extend the chain only if we got a usable response. On failure, return the
    # caller's prior_history unchanged so the next retry doesn't pollute the
    # conversation with a failed turn.
    if output_image is not None and model_content is not None:
        next_history = list(req.prior_history) + [user_content, model_content]
    else:
        next_history = list(req.prior_history)

    record_generation(
        GenerationRecord(
            generation_id=generation_id,
            timestamp=time.time(),
            model_id=req.model_id,
            resolution=req.resolution,
            num_ref_images=num_refs,
            actual_cost=actual_cost,
            status=status,
            output_path=str(output_path) if output_path else None,
            error_message=last_error if status == "failed" else None,
            prompt_summary=_build_prompt_summary(req),
            leg_id=req.leg_id,
            upholstery_color=req.upholstery_color,
            upholstery_material=req.upholstery_material,
            camera_angle=req.camera_angle,
            turn_number=req.turn_number,
            elapsed_ms=elapsed_ms,
        )
    )

    return GenerationResult(
        success=output_image is not None,
        generation_id=generation_id,
        output_path=output_path,
        output_image=output_image,
        next_history=next_history,
        actual_cost=actual_cost,
        attempts=attempts_made,
        # User-facing PL message on failure; raw technical string kept as detail.
        error_message=err_info.message_pl if err_info else None,
        error_code=err_info.error_code if err_info else None,
        error_detail=(last_error or err_info.message_en) if err_info else None,
        retryable=err_info.retryable if err_info else False,
        http_status=err_info.http_status if err_info else 500,
        elapsed_ms=elapsed_ms,
        model_id=req.model_id,
        resolution=req.resolution,
    )


def _sleep_backoff(attempt: int) -> None:
    delay = min(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), _BACKOFF_MAX_SECONDS)
    logger.info("Backing off %.1f seconds before retry...", delay)
    time.sleep(delay)


def _build_prompt_summary(req: GenerationRequest) -> str:
    parts = [
        req.upholstery_color,
        req.upholstery_material,
        req.leg_id or "existing-legs",
        req.camera_angle,
        req.resolution,
    ]
    return " | ".join(parts)


def validate_request(req: GenerationRequest) -> list[str]:
    """
    Return a list of validation error strings. Empty list = valid.
    Called before submission to surface errors in the UI without making an API call.
    """
    errors: list[str] = []

    # Model must be in the schema enum
    if req.model_id not in schema.model_ids:
        errors.append(f"Unknown model ID: {req.model_id!r}. Must be one of: {schema.model_ids}")

    # Resolution ceiling per model
    allowed_resolutions = schema.resolution_choices_for_model(req.model_id)
    if req.resolution not in allowed_resolutions:
        errors.append(
            f"Resolution {req.resolution!r} is not available on {req.model_id}. "
            f"Allowed: {allowed_resolutions}"
        )

    # Reference slot ceiling
    num_refs = _count_active_refs(req)
    max_refs = schema.max_refs_for_model(req.model_id)
    if num_refs > max_refs:
        errors.append(
            f"Too many reference images: {num_refs} slots filled but {req.model_id} "
            f"allows a maximum of {max_refs}. Remove slot 4 (swatch) or use a preview-tier model."
        )

    # Shadow direction required when legs or scene are swapped
    has_leg_swap = req.leg_id is not None
    has_scene = req.scene_reference_image is not None
    if (has_leg_swap or has_scene) and not req.shadow_direction:
        errors.append(
            "Shadow direction is required when a leg or scene reference is active. "
            "Fill the shadow direction field (e.g. '4 o-clock')."
        )

    # On Flash (3-ref cap), the swatch slot is reachable only when the total
    # active refs are still <= 3. The total-refs check above handles this; no
    # separate "preview only" rule is needed (the schema's slot_3_scene_or_swatch
    # explicitly allows swatch in slot 3 on Flash when scene is absent).

    # Preserve list must not be empty; base image is required. Neither rule
    # applies to freeform/editorial requests, which are pure text-to-image.
    if not req.freeform_prompt:
        if not req.preserve_list:
            errors.append("Preserve list must contain at least one item.")
        if req.base_product_image is None:
            errors.append("A base product image is required (slot 1).")

    # Multi-turn chain-reset warning (not an error, but surfaces as warning)
    if req.turn_number > 3:
        errors.append(
            f"WARNING: Turn {req.turn_number} exceeds the recommended chain length of 3. "
            "Identity drift (stitching, leg joinery) is expected at this turn depth. "
            "Save the current output and start a new chain with it as the base reference."
        )

    return errors
