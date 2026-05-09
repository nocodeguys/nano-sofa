"""
generate.py — Tab 1: "Generuj wariant"

Schema-driven, step-by-step formularz w języku polskim.
Wszystkie ograniczenia z model_constraints są egzekwowane na poziomie
formularza, więc niewłaściwe konfiguracje są blokowane przed wywołaniem API.

Sekcje (kroki):
  1. Zdjęcie produktu i typ
  2. Model i rozdzielczość
  3. Wariant (kolor, materiał, rozmiar)
  4. Nogi / styl ramy (opcjonalne)
  5. Dodatkowe referencje (scena + próbka)
  6. Kamera i światło
  7. Zaawansowane (preserve, negatywy, multi-turn, system, notatki)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import gradio as gr

from app.core.cost_tracker import estimate_cost, session_total
from app.core.generator import GenerationRequest, GenerationResult, generate, validate_request
from app.core.leg_browser import leg_browser
from app.core.schema_loader import schema

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Default preserve list dla typu "sofa". Dla "łóżko" stosowany jest inny zestaw,
# zob. schema.default_preserve_by_type.
_DEFAULT_PRESERVE = schema.default_preserve_by_type["sofa"]

# Curated kolory dla zdjęć produktów. Dropdown akceptuje też wartości spoza
# listy (allow_custom_value=True) — można wpisać dowolny opis.
_COLOR_PRESETS = [
    "kość słoniowa",
    "krem",
    "szarość gołębia",
    "grafit",
    "czarny",
    "wielbłądzi",
    "opalona",
    "brązowy czekoladowy",
    "terakota",
    "rdza",
    "musztardowy",
    "oliwkowy",
    "szałwiowy",
    "ciemnozielony",
    "granatowy",
    "błękit pudrowy",
    "bordowy",
    "różowy pudrowy",
]

# Mapowania PL → EN dla wartości wysyłanych do modelu.
# Model lepiej rozumie angielskie nazwy materiałów / typów.
_PRODUCT_TYPE_PL = {"sofa": "sofa", "łóżko": "bed"}
_PRODUCT_TYPE_EN_TO_PL = {"sofa": "sofa", "bed": "łóżko"}

_MATERIAL_LABELS_PL = {
    "bouclé": "bouclé",
    "linen": "len",
    "cotton-velvet": "aksamit bawełniany",
    "performance-velvet": "aksamit techniczny",
    "wool-blend": "mieszanka wełny",
    "leather-aniline": "skóra anilinowa",
    "leather-pigmented": "skóra licowa",
    "chenille": "szenila",
    "tweed": "tweed",
}

_FRAME_STYLE_LABELS_PL = {
    "platform": "platforma",
    "low-profile-platform": "niska platforma",
    "panel": "panelowa",
    "sleigh": "sankowa",
    "four-poster": "czterosłupkowa",
    "canopy": "z baldachimem",
    "divan": "tapczan / divan",
    "ottoman-storage": "z pojemnikiem (ottoman)",
    "captain": "kapitańska",
    "upholstered-platform": "platforma tapicerowana",
    "upholstered-headboard-only": "tylko zagłówek tapicerowany",
}

_SOFA_CONFIG_LABELS_PL = {
    "1-seater": "1-osobowa",
    "2-seater": "2-osobowa",
    "3-seater": "3-osobowa",
    "4-seater": "4-osobowa",
    "corner-left": "narożnik lewy",
    "corner-right": "narożnik prawy",
    "modular": "modułowa",
}

_BED_CONFIG_LABELS_PL = {
    "twin": "twin (90×200)",
    "full": "full / double (140×200)",
    "queen": "queen (160×200)",
    "king": "king (180×200)",
    "california-king": "california king",
    "european-single": "europejskie 1-os. (90×200)",
    "european-double": "europejskie 2-os. (160×200)",
    "european-king": "europejskie king (180×200)",
    "super-king": "super king (200×200)",
}

_CAMERA_ANGLE_LABELS_PL = {
    "front-0": "przód (0°)",
    "front-34-left": "przód-lewo (34°)",
    "front-34-right": "przód-prawo (34°)",
    "side-90": "bok (90°)",
    "low-34": "niski 34°",
}


def _config_choices(product_type_pl: str) -> list[tuple[str, str]]:
    """Returns (label_pl, value) pairs for the configuration dropdown."""
    type_en = _PRODUCT_TYPE_PL.get(product_type_pl, "sofa")
    raw = schema.configurations_by_type.get(type_en, [])
    label_map = _BED_CONFIG_LABELS_PL if type_en == "bed" else _SOFA_CONFIG_LABELS_PL
    return [(label_map.get(r, r), r) for r in raw]


def _frame_style_choices() -> list[tuple[str, str]]:
    return [(_FRAME_STYLE_LABELS_PL.get(s, s), s) for s in schema.frame_style_options]


def _material_choices() -> list[tuple[str, str]]:
    return [(_MATERIAL_LABELS_PL.get(m, m), m) for m in schema.material_options]


def _camera_angle_choices() -> list[tuple[str, str]]:
    return [(_CAMERA_ANGLE_LABELS_PL.get(a, a), a) for a in schema.angle_options]


def _model_info_text(model_id: str) -> str:
    mc = schema.model_constraints.get(model_id, {})
    max_refs = mc.get("max_reference_images", "?")
    max_res = mc.get("max_output_resolution", "?")
    dep = mc.get("deprecation_date")
    dep_str = f" • Wycofanie: {dep}" if dep else ""
    thinking = " • Tryb myślenia: domyślnie włączony" if mc.get("thinking_on_by_default") else ""
    cannot_disable = " (niewyłączalny)" if mc.get("thinking_cannot_be_disabled") else ""
    return f"Maks. referencji: {max_refs} • Maks. rozdzielczość: {max_res}{dep_str}{thinking}{cannot_disable}"


def _count_active_refs(
    leg_choice: Optional[str],
    scene_image: Optional[Any],
    swatch_image: Optional[Any],
) -> int:
    count = 1
    if leg_choice and leg_choice != "Brak — zachowaj obecne nogi":
        count += 1
    if scene_image is not None:
        count += 1
    if swatch_image is not None:
        count += 1
    return count


def _update_cost_preview(
    model_id: str,
    resolution: str,
    leg_choice: Optional[str],
    scene_image: Optional[Any],
    swatch_image: Optional[Any],
) -> str:
    num_refs = _count_active_refs(leg_choice, scene_image, swatch_image)
    est = estimate_cost(model_id, resolution, num_refs)
    breakdown = est.format_breakdown()
    pl_breakdown = (
        breakdown
        .replace("Output image", "Wygenerowany obraz")
        .replace("Input images", "Obrazy wejściowe")
        .replace("Text input", "Tekst wejściowy")
        .replace("Thinking tokens (est.)", "Tokeny myślenia (szac.)")
        .replace("Total estimate", "Łączny szacunek")
        .replace("(Batch pricing applied — 50% discount)", "(Cennik wsadowy — rabat 50%)")
    )
    session_cost = session_total()
    return (
        f"**Szacunkowy koszt — to wygenerowanie**\n\n{pl_breakdown}\n\n"
        f"**Suma w sesji:** ${session_cost:.4f}"
    )


def _update_model_constraints(model_id: str) -> tuple:
    info = _model_info_text(model_id)
    res_choices = schema.resolution_choices_for_model(model_id)
    return (
        gr.update(value=info),
        gr.update(choices=res_choices, value=res_choices[0]),
    )


def _on_leg_select(leg_label: str, camera_angle: str) -> tuple:
    if not leg_label or leg_label == "Brak — zachowaj obecne nogi":
        return gr.update(value=""), gr.update()
    leg_id = leg_browser.id_from_label(leg_label)
    if not leg_id:
        return gr.update(value=""), gr.update()
    entry = leg_browser.get(leg_id)
    if not entry:
        return gr.update(value=""), gr.update()
    return (
        gr.update(value=entry.explicit_descriptor),
        gr.update(value=entry.shadow_direction_hint),
    )


def _on_generate(
    api_key: str,
    # Product type
    product_type_pl: str,
    frame_style: Optional[str],
    # Model
    model_id: str,
    # References
    base_product_image,
    scene_image,
    swatch_image,
    # Product
    sofa_configuration: str,
    leg_count: int,
    preserve_list: list[str],
    # Upholstery
    upholstery_color: str,
    upholstery_material: str,
    texture_notes: str,
    base_image_has_alpha: bool,
    # Legs
    leg_dropdown: str,
    leg_explicit_descriptor: str,
    # Camera
    camera_angle: str,
    shadow_direction: str,
    focal_length_mm: int,
    aperture: str,
    framing: str,
    # Output
    aspect_ratio: str,
    resolution: str,
    output_style: str,
    # System / negative
    system_instruction: str,
    negative_text: str,
    # Notes
    notes: str,
    # Multi-turn
    turn_number: int,
    # State
    session_history: list,
) -> tuple:
    if base_product_image is None:
        return (
            None,
            "**Błąd:** Wgraj zdjęcie produktu (Krok 1) zanim klikniesz Generuj.",
            gr.update(),
            session_history,
            turn_number,
        )

    leg_id: Optional[str] = None
    leg_render_path: Optional[Path] = None
    if leg_dropdown and leg_dropdown != "Brak — zachowaj obecne nogi":
        leg_id = leg_browser.id_from_label(leg_dropdown)
        if leg_id:
            leg_render_path = leg_browser.render_path_for(leg_id, camera_angle)

    preserve = preserve_list if preserve_list else _DEFAULT_PRESERVE
    neg_items = [ln.strip() for ln in negative_text.splitlines() if ln.strip()]
    angle_degrees = schema.angle_to_degrees.get(camera_angle, 35)

    product_type_en = _PRODUCT_TYPE_PL.get(product_type_pl, "sofa")

    req = GenerationRequest(
        api_key=api_key or "",
        model_id=model_id,
        base_product_image=base_product_image,
        leg_reference_image=leg_render_path,
        scene_reference_image=scene_image,
        swatch_reference_image=swatch_image,
        product_type=product_type_en,
        frame_style=frame_style if product_type_en == "bed" else None,
        sofa_configuration=sofa_configuration,
        leg_count=int(leg_count),
        preserve_list=preserve,
        upholstery_color=upholstery_color,
        upholstery_material=upholstery_material,
        texture_notes=texture_notes,
        base_image_has_alpha=base_image_has_alpha,
        leg_id=leg_id,
        leg_explicit_descriptor=leg_explicit_descriptor,
        camera_angle=camera_angle,
        angle_degrees_from_left=angle_degrees,
        shadow_direction=shadow_direction,
        focal_length_mm=focal_length_mm,
        aperture=aperture,
        framing=framing,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        output_style=output_style,
        system_instruction=system_instruction,
        negative_list=neg_items,
        notes=notes,
        turn_number=turn_number,
        prior_history=session_history,
    )

    errors = validate_request(req)
    hard_errors = [e for e in errors if not e.startswith("WARNING:")]
    warnings = [e for e in errors if e.startswith("WARNING:")]

    if hard_errors:
        error_md = "**Błędy walidacji — popraw przed wygenerowaniem:**\n" + "\n".join(
            f"- {e}" for e in hard_errors
        )
        return None, error_md, gr.update(), session_history, turn_number

    warning_md = ""
    if warnings:
        warning_md = "\n".join(f"> {w}" for w in warnings) + "\n\n"

    result: GenerationResult = generate(req)

    if result.success:
        cost_md = (
            f"**Ten obraz:** ${result.actual_cost:.4f}  •  "
            f"**Suma w sesji:** ${session_total():.4f}"
        )
        status_md = (
            f"{warning_md}"
            f"**Wygenerowano pomyślnie** — {result.model_id} — {result.resolution}\n\n"
            f"ID generacji: `{result.generation_id}`\n\n"
            f"Próby: {result.attempts}  •  Zapisano: `{result.output_path}`"
        )
        new_turn = turn_number + 1
        new_history = result.next_history
    else:
        cost_md = f"**Suma w sesji:** ${session_total():.4f}"
        status_md = (
            f"{warning_md}"
            f"**Generacja nieudana** po {result.attempts} próbie(ach)\n\n"
            f"{result.error_message}"
        )
        new_turn = turn_number
        new_history = session_history

    return (
        result.output_image,
        status_md,
        cost_md,
        new_history,
        new_turn,
    )


def build_tab(api_key_input: gr.Textbox) -> None:
    """Build the Generate Variant tab UI. Called inside a gr.Tab() context.
    `api_key_input` is the shared password Textbox from main.py — passed in
    so this tab can include its current value in click() inputs without
    needing a global state.
    """

    gr.Markdown(
        "Wypełnij kroki w kolejności. Pola opcjonalne są domyślnie zwinięte. "
        "Walidacja blokuje błędne kombinacje przed wywołaniem API.",
    )

    # ================================================================== #
    # KROK 1 — Zdjęcie produktu i typ
    # ================================================================== #
    with gr.Accordion("Krok 1 — Zdjęcie produktu i typ", open=True):
        with gr.Row():
            with gr.Column(scale=2):
                base_product_image = gr.Image(
                    label="Zdjęcie bazowe produktu (wymagane)",
                    type="pil",
                    sources=["upload"],
                    height=280,
                )
                alpha_warning = gr.Markdown(visible=False)
                base_image_has_alpha = gr.Checkbox(
                    label="Zdjęcie ma kanał alfa (przezroczyste tło) — zostanie spłaszczone do 18% szarości",
                    value=False,
                )
            with gr.Column(scale=1):
                product_type = gr.Radio(
                    choices=list(_PRODUCT_TYPE_PL.keys()),
                    value="sofa",
                    label="Typ produktu",
                    info="Steruje słownictwem promptu i dostępnymi polami. Wybierz 'łóżko' aby uniknąć dorabiania nóg do platformy.",
                )

    # ================================================================== #
    # KROK 2 — Model AI i rozdzielczość
    # ================================================================== #
    with gr.Accordion("Krok 2 — Model AI", open=True):
        with gr.Row():
            with gr.Column():
                model_id = gr.Dropdown(
                    choices=schema.model_ids,
                    value=schema.model_ids[0],
                    label="Model Gemini",
                    info="Ograniczenia (referencje / rozdzielczość) aktualizują się automatycznie",
                )
                model_info_md = gr.Markdown(_model_info_text(schema.model_ids[0]))
            with gr.Column():
                aspect_ratio = gr.Dropdown(
                    choices=schema.aspect_ratio_options,
                    value="4:3",
                    label="Proporcje",
                )
                resolution = gr.Dropdown(
                    choices=schema.resolution_choices_for_model(schema.model_ids[0]),
                    value="1K",
                    label="Rozdzielczość",
                    info="Flash GA jest ograniczony do 1K — formularz to wymusza",
                )

    # ================================================================== #
    # KROK 3 — Wariant (kolor, materiał, konfiguracja, styl ramy dla łóżek)
    # ================================================================== #
    with gr.Accordion("Krok 3 — Wariant (kolor, materiał, rozmiar)", open=True):
        with gr.Row():
            with gr.Column():
                upholstery_color = gr.Dropdown(
                    label="Kolor",
                    choices=_COLOR_PRESETS,
                    value="szałwiowy",
                    allow_custom_value=True,
                    info="Wybierz preset lub wpisz własny opis (np. 'ciepła szałwia z szarym podtonem').",
                )
                upholstery_material = gr.Dropdown(
                    choices=_material_choices(),
                    value="bouclé",
                    label="Materiał / tkanina",
                    info="Zamknięta lista — to materiały, które model rysuje najwierniej.",
                )
                texture_notes = gr.Textbox(
                    label="Notatki o teksturze (opcjonalne)",
                    lines=2,
                    placeholder="Dla bouclé: gęstość pętelek. Dla aksamitu: kierunek włosa względem kamery.",
                )
            with gr.Column():
                sofa_configuration = gr.Dropdown(
                    choices=_config_choices("sofa"),
                    value="3-seater",
                    label="Konfiguracja / rozmiar",
                    info="Sofa: liczba miejsc. Łóżko: rozmiar materaca. Lista zmienia się z typem produktu.",
                )
                frame_style = gr.Dropdown(
                    choices=_frame_style_choices(),
                    value=None,
                    label="Styl ramy łóżka",
                    info="Tylko dla łóżek. Steruje sylwetką ramy w prompcie.",
                    visible=False,
                )

    # ================================================================== #
    # KROK 4 — Nogi / styl ramy (opcjonalne)
    # ================================================================== #
    with gr.Accordion("Krok 4 — Nogi (opcjonalne — domyślnie zachowuje obecne)", open=False):
        with gr.Row():
            with gr.Column():
                leg_options = ["Brak — zachowaj obecne nogi"] + [
                    e.display_label for e in leg_browser.entries.values()
                ]
                leg_dropdown = gr.Dropdown(
                    choices=leg_options,
                    value="Brak — zachowaj obecne nogi",
                    label="Styl nóg",
                    info="Opcjonalne. Domyślnie zachowuje nogi ze zdjęcia bazowego. Wybór presetu auto-wypełnia opis i kierunek cienia.",
                )
                leg_explicit_descriptor = gr.Textbox(
                    label="Dokładny opis nóg (auto-uzupełniany, edytowalny)",
                    lines=2,
                    placeholder="np. cztery stożkowate cylindryczne nogi, lity orzech satynowy, bez żadnych łączników",
                    info="Sygnał tekst+obraz — kluczowa mitygacja dla 'leg-geometry-morphing'.",
                )
            with gr.Column():
                leg_count = gr.Slider(
                    minimum=schema.leg_count_min,
                    maximum=schema.leg_count_max,
                    value=4,
                    step=1,
                    label="Liczba nóg",
                    info="Ustaw 0 dla łóżek platformowych / divanów bez widocznych nóg — prompt wtedy POMINIE wzmianki o liczbie nóg.",
                )

    # ================================================================== #
    # KROK 5 — Dodatkowe referencje (scena + próbka)
    # ================================================================== #
    with gr.Accordion("Krok 5 — Dodatkowe referencje (opcjonalne)", open=False):
        gr.Markdown(
            "Każda referencja zajmuje slot — Flash GA ma limit 3 slotów (baza + 2 opcjonalne). "
            "Modele preview pozwalają na więcej. Status poniżej pokazuje aktualne wykorzystanie."
        )
        with gr.Row():
            scene_image = gr.Image(
                label="Referencja sceny (opcjonalna)",
                type="pil",
                sources=["upload"],
                height=180,
            )
            swatch_image = gr.Image(
                label="Próbka materiału (opcjonalna)",
                type="pil",
                sources=["upload"],
                height=180,
            )
        ref_slot_status = gr.Markdown("**Sloty referencji:** 1 (baza) + 0 opcjonalnych.")

    # ================================================================== #
    # KROK 6 — Kamera i światło
    # ================================================================== #
    with gr.Accordion("Krok 6 — Kamera i światło", open=False):
        with gr.Row():
            with gr.Column():
                camera_angle = gr.Dropdown(
                    choices=_camera_angle_choices(),
                    value="front-34-left",
                    label="Kąt kamery",
                )
                shadow_direction = gr.Textbox(
                    label="Kierunek cienia (zegarowo)",
                    value="4 o-clock",
                    placeholder="np. 4 o-clock, 8 o-clock, 6 o-clock",
                    info="Wymagane gdy aktywna jest zmiana nóg lub scena — mitygacja niespójnych cieni.",
                )
            with gr.Column():
                focal_length_mm = gr.Slider(
                    minimum=24,
                    maximum=135,
                    value=50,
                    step=1,
                    label="Ogniskowa (ekwiwalent mm)",
                )
                aperture = gr.Textbox(label="Przysłona", value="f/4.5")
                framing = gr.Textbox(
                    label="Kadrowanie",
                    value="full product visible with breathing room above and below",
                    lines=2,
                )

    # ================================================================== #
    # KROK 7 — Zaawansowane (preserve, negatywy, system, multi-turn, notatki)
    # ================================================================== #
    with gr.Accordion("Krok 7 — Zaawansowane", open=False):
        with gr.Row():
            with gr.Column():
                preserve_list = gr.CheckboxGroup(
                    choices=schema.preserve_options,
                    value=_DEFAULT_PRESERVE,
                    label="Lista do zachowania (NIE zmieniać)",
                    info="Najważniejsze pole — pominięcia powodują niejawne przeprojektowanie. Wartości domyślne dostosowują się do typu produktu.",
                )
                output_style = gr.Textbox(
                    label="Styl wyjścia",
                    value=schema.style_default,
                    lines=2,
                )
            with gr.Column():
                system_instruction = gr.Textbox(
                    label="Instrukcja systemowa (persona modelu)",
                    value=schema.system_instruction_default,
                    lines=5,
                    info="Najsilniejsza pojedyncza mitygacja niejawnego przeprojektowania.",
                )
                negative_text = gr.Textbox(
                    label="Lista negatywna (jedna pozycja na linię)",
                    value="\n".join(schema.negative_defaults),
                    lines=6,
                    info="Wstępnie wypełnione z domyślnymi schematu.",
                )

        gr.Markdown("### Multi-turn (sesja edycyjna)")
        with gr.Row():
            with gr.Column():
                turn_number_display = gr.Number(
                    label="Numer bieżącego etapu",
                    value=1,
                    precision=0,
                    interactive=False,
                )
                history_depth_md = gr.Markdown(
                    "**Głębokość historii:** 0 wcześniejszych etapów. Pełna konwersacja "
                    "(z thought_signature) jest auto-przekazywana do modelu — mitygacja dryfu tożsamości."
                )
                chain_reset_btn = gr.Button("Resetuj łańcuch (rozpocznij nową sesję)", variant="secondary")
            with gr.Column():
                notes = gr.Textbox(
                    label="Notatki (dowolny tekst — trafia dosłownie do promptu)",
                    lines=4,
                    placeholder="Jednorazowe instrukcje, które nie pasują do innych pól.",
                )

    gr.Markdown("---")

    # ================================================================== #
    # GENEROWANIE
    # ================================================================== #
    with gr.Row():
        with gr.Column(scale=2):
            cost_preview_md = gr.Markdown("**Szacunkowy koszt:** zmień model lub sloty aby zaktualizować.")
            generate_btn = gr.Button("Generuj wariant", variant="primary", size="lg")
        with gr.Column(scale=1):
            session_cost_md = gr.Markdown(f"**Suma w sesji:** ${session_total():.4f}")

    gr.Markdown("---")

    with gr.Row():
        with gr.Column(scale=1):
            output_image = gr.Image(
                label="Wygenerowany obraz",
                type="pil",
                height=500,
                interactive=False,
            )
        with gr.Column(scale=1):
            status_md = gr.Markdown("Gotowy.")
            cost_result_md = gr.Markdown("")

    # ------------------------------------------------------------------ #
    # State
    # ------------------------------------------------------------------ #
    session_history = gr.State([])
    turn_number_state = gr.State(1)

    # ------------------------------------------------------------------ #
    # Event wiring
    # ------------------------------------------------------------------ #

    # Product type change → update configuration choices, frame style visibility,
    # leg-count default, default preserve list.
    def _on_product_type_change(new_type_pl: str):
        new_type_en = _PRODUCT_TYPE_PL.get(new_type_pl, "sofa")
        configs = _config_choices(new_type_pl)
        default_config = configs[0][1] if configs else ""
        is_bed = new_type_en == "bed"
        default_legs = 0 if is_bed else 4
        default_preserve = schema.default_preserve_by_type.get(new_type_en, [])
        return (
            gr.update(choices=configs, value=default_config),
            gr.update(visible=is_bed, value=None),
            gr.update(value=default_legs),
            gr.update(value=default_preserve),
        )

    product_type.change(
        fn=_on_product_type_change,
        inputs=[product_type],
        outputs=[sofa_configuration, frame_style, leg_count, preserve_list],
    )

    # Model change → update constraints and resolution choices
    model_id.change(
        fn=_update_model_constraints,
        inputs=[model_id],
        outputs=[model_info_md, resolution],
    )

    # Cost preview updates
    for trigger in [model_id, resolution, leg_dropdown, scene_image, swatch_image]:
        trigger.change(
            fn=_update_cost_preview,
            inputs=[model_id, resolution, leg_dropdown, scene_image, swatch_image],
            outputs=[cost_preview_md],
        )

    # Leg selection auto-fill
    leg_dropdown.change(
        fn=_on_leg_select,
        inputs=[leg_dropdown, camera_angle],
        outputs=[leg_explicit_descriptor, shadow_direction],
    )

    # Reference slot count display
    def _update_ref_slots(leg_choice, scene_img, swatch_img, model):
        count = _count_active_refs(leg_choice, scene_img, swatch_img)
        max_refs = schema.max_refs_for_model(model)
        if count > max_refs:
            status = f"**Sloty referencji: {count} / {max_refs} — POWYŻEJ LIMITU dla {model}**"
        elif count == max_refs:
            status = f"**Sloty referencji: {count} / {max_refs} — przy limicie {model}**"
        else:
            status = f"**Sloty referencji:** {count} / {max_refs} aktywnych"
        return gr.update(value=status)

    for trigger in [leg_dropdown, scene_image, swatch_image, model_id]:
        trigger.change(
            fn=_update_ref_slots,
            inputs=[leg_dropdown, scene_image, swatch_image, model_id],
            outputs=[ref_slot_status],
        )

    # Alpha channel detection
    def _check_alpha(image):
        if image is None:
            return gr.update(visible=False, value="")
        if hasattr(image, "mode") and image.mode in ("RGBA", "LA"):
            return gr.update(
                visible=True,
                value=(
                    "> **Wykryto kanał alfa** w zdjęciu produktu. "
                    "Zaznacz pole 'Zdjęcie ma kanał alfa' aby spłaszczyć tło do 18% szarości "
                    "(zapobiega problemowi 'background-bleed')."
                ),
            )
        return gr.update(visible=False, value="")

    base_product_image.change(
        fn=_check_alpha,
        inputs=[base_product_image],
        outputs=[alpha_warning],
    )

    # Chain reset
    def _reset_chain():
        return (
            [],
            1,
            gr.update(value=1),
            gr.update(
                value=(
                    "**Głębokość historii:** 0 wcześniejszych etapów. Pełna konwersacja "
                    "(z thought_signature) jest auto-przekazywana do modelu — mitygacja dryfu tożsamości."
                )
            ),
        )

    chain_reset_btn.click(
        fn=_reset_chain,
        inputs=[],
        outputs=[session_history, turn_number_state, turn_number_display, history_depth_md],
    )

    # Generate
    generate_btn.click(
        fn=_on_generate,
        inputs=[
            api_key_input,
            product_type,
            frame_style,
            model_id,
            base_product_image,
            scene_image,
            swatch_image,
            sofa_configuration,
            leg_count,
            preserve_list,
            upholstery_color,
            upholstery_material,
            texture_notes,
            base_image_has_alpha,
            leg_dropdown,
            leg_explicit_descriptor,
            camera_angle,
            shadow_direction,
            focal_length_mm,
            aperture,
            framing,
            aspect_ratio,
            resolution,
            output_style,
            system_instruction,
            negative_text,
            notes,
            turn_number_state,
            session_history,
        ],
        outputs=[
            output_image,
            status_md,
            cost_result_md,
            session_history,
            turn_number_state,
        ],
    )

    # Sync turn display + history depth after each turn
    def _sync_turn_display(turn_state, history_state):
        prior_turns = len(history_state) // 2 if history_state else 0
        depth_md = (
            f"**Głębokość historii:** {prior_turns} wcześniejszych etapów. "
            "Pełna konwersacja (z thought_signature) jest auto-przekazywana do modelu."
        )
        if turn_state > 3:
            depth_md += (
                "\n\n> **Zalecany reset łańcucha:** "
                f"Etap {turn_state} przekracza 3. "
                "Zapisz bieżący wynik i zacznij nowy łańcuch z nim jako bazą, "
                "aby uniknąć dryfu tożsamości."
            )
        return gr.update(value=turn_state), gr.update(value=depth_md)

    turn_number_state.change(
        fn=_sync_turn_display,
        inputs=[turn_number_state, session_history],
        outputs=[turn_number_display, history_depth_md],
    )
