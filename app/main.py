"""
main.py — Nano Sofa: Gradio application entry point (PL UI).

Tabs (Polish labels):
  1. Generuj wariant — pełny formularz krok-po-kroku
  2. Porównaj / Wsadowo — galeria i kolejka wariantów
  3. Koszty — śledzenie wydatków
  4. Schemat / Nogi — przeglądarka schematu i biblioteki nóg

Run with:
    python app/main.py

API key is entered in the UI by each user — no environment variable required.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure repo root is on the Python path so imports like `app.core.*` resolve
# regardless of where the user runs the script from.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import gradio as gr

from app.tabs import compare, costs, generate, schemas


# --------------------------------------------------------------------------- #
# Modern theme — Linear / Vercel-inspired
# --------------------------------------------------------------------------- #

_THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.slate,
    secondary_hue=gr.themes.colors.gray,
    neutral_hue=gr.themes.colors.gray,
    radius_size=gr.themes.sizes.radius_md,
    spacing_size=gr.themes.sizes.spacing_md,
    text_size=gr.themes.sizes.text_md,
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "monospace"],
).set(
    # Surfaces
    body_background_fill="#fafafa",
    background_fill_primary="#ffffff",
    background_fill_secondary="#fafafa",
    block_background_fill="#ffffff",
    block_border_width="1px",
    block_border_color="#e5e7eb",
    block_label_background_fill="transparent",
    block_label_text_color="#374151",
    block_title_text_color="#0f172a",
    block_title_text_weight="600",
    panel_background_fill="#ffffff",
    panel_border_color="#e5e7eb",
    # Inputs
    input_background_fill="#ffffff",
    input_border_color="#e5e7eb",
    input_border_color_focus="#0f172a",
    input_shadow_focus="0 0 0 3px rgba(15,23,42,0.08)",
    input_radius="*radius_md",
    # Buttons
    button_primary_background_fill="#0f172a",
    button_primary_background_fill_hover="#1e293b",
    button_primary_text_color="#ffffff",
    button_primary_border_color="#0f172a",
    button_secondary_background_fill="#ffffff",
    button_secondary_background_fill_hover="#f8fafc",
    button_secondary_text_color="#0f172a",
    button_secondary_border_color="#e5e7eb",
    button_large_radius="*radius_md",
    button_small_radius="*radius_md",
    # Shadows
    shadow_drop="0 1px 2px rgba(0,0,0,0.04)",
    shadow_drop_lg="0 4px 12px rgba(0,0,0,0.08)",
    # Body text
    body_text_color="#0f172a",
    body_text_color_subdued="#64748b",
    # Borders
    border_color_accent="#0f172a",
    border_color_primary="#e5e7eb",
)


# Custom CSS layered on top of the theme for things tokens don't reach
# (accordion appearance, tab nav, image dropzones, banners).
_CSS = """
.gradio-container {
    max-width: 1280px !important;
}

/* --- Page header --- */
.gradio-container h1 {
    font-size: 2rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    color: #0f172a !important;
    margin: 24px 0 8px 0 !important;
}

.gradio-container h2 {
    font-size: 1.25rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
    color: #0f172a !important;
}

/* --- Tabs: modern pill style --- */
.tab-nav, .tabs > div:first-child {
    background: transparent !important;
    border-bottom: 1px solid #e5e7eb !important;
    gap: 4px !important;
    padding: 4px 0 0 0 !important;
}

.tab-nav button, .tabs > div:first-child button {
    background: transparent !important;
    border: none !important;
    border-radius: 8px 8px 0 0 !important;
    padding: 10px 16px !important;
    font-weight: 500 !important;
    color: #64748b !important;
    transition: color 0.15s ease, background 0.15s ease !important;
    border-bottom: 2px solid transparent !important;
    margin-bottom: -1px !important;
}

.tab-nav button:hover, .tabs > div:first-child button:hover {
    color: #0f172a !important;
    background: #f8fafc !important;
}

.tab-nav button.selected, .tabs > div:first-child button.selected {
    color: #0f172a !important;
    background: transparent !important;
    border-bottom: 2px solid #0f172a !important;
    font-weight: 600 !important;
}

/* --- Accordions: card-like with subtle shadow --- */
details, .accordion {
    background: #ffffff !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 12px !important;
    margin-bottom: 12px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
    overflow: hidden !important;
}

summary, details > summary, .accordion > .label-wrap {
    padding: 16px 20px !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    color: #0f172a !important;
    cursor: pointer !important;
    background: #ffffff !important;
    transition: background 0.15s ease !important;
    list-style: none !important;
}

summary:hover, details > summary:hover, .accordion > .label-wrap:hover {
    background: #f8fafc !important;
}

details[open] > summary {
    border-bottom: 1px solid #e5e7eb !important;
}

/* Inner content padding for accordions */
details[open] > div, .accordion-content {
    padding: 16px 20px 20px 20px !important;
}

/* --- Image upload dropzones --- */
.image-container, [data-testid="image"] {
    border: 1px dashed #d1d5db !important;
    border-radius: 12px !important;
    background: #fafafa !important;
    transition: border-color 0.15s ease, background 0.15s ease !important;
}

.image-container:hover, [data-testid="image"]:hover {
    border-color: #0f172a !important;
    background: #f8fafc !important;
}

/* --- Buttons: bigger primary, hover lift --- */
button.lg.primary, button[variant="primary"] {
    background: #0f172a !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 12px 24px !important;
    transition: background 0.15s ease, transform 0.1s ease, box-shadow 0.15s ease !important;
}

button.lg.primary:hover, button[variant="primary"]:hover {
    background: #1e293b !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(15,23,42,0.15) !important;
}

button.lg.primary:active, button[variant="primary"]:active {
    transform: translateY(0);
}

/* --- API key banner --- */
.api-key-row {
    background: linear-gradient(180deg, #ffffff 0%, #fafafa 100%) !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 12px !important;
    padding: 20px 24px !important;
    margin: 16px 0 24px 0 !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
}

/* --- Radio / checkbox groups --- */
.gr-radio, fieldset {
    gap: 6px !important;
}

.gr-radio label, fieldset label {
    border-radius: 8px !important;
    padding: 8px 14px !important;
    border: 1px solid #e5e7eb !important;
    background: #ffffff !important;
    transition: all 0.15s ease !important;
    cursor: pointer !important;
}

.gr-radio label:hover, fieldset label:hover {
    border-color: #cbd5e1 !important;
    background: #f8fafc !important;
}

/* --- Markdown / status / blockquotes --- */
.gradio-container blockquote {
    background: #fffbeb !important;
    border-left: 3px solid #f59e0b !important;
    padding: 12px 16px !important;
    border-radius: 6px !important;
    color: #78350f !important;
    margin: 12px 0 !important;
}

.gradio-container code {
    background: #f1f5f9 !important;
    color: #0f172a !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-size: 0.875em !important;
}

/* --- Step heading aux classes --- */
.step-heading {
    font-size: 1.05em;
    font-weight: 600;
    color: #0f172a;
    padding: 6px 0 4px 0;
}

.step-subtext {
    font-size: 0.85em;
    color: #64748b;
    padding: 0 0 8px 0;
}

/* --- Cost highlight --- */
.cost-highlight { font-weight: 600; color: #166534; }

/* --- Smooth transitions everywhere --- */
* {
    transition-property: color, background-color, border-color, box-shadow !important;
    transition-duration: 0.15s !important;
    transition-timing-function: ease !important;
}
"""


_TITLE = "Nano Sofa — Generator zdjęć produktów"
_DESCRIPTION = (
    "Twórz i porównuj warianty kanap i łóżek z wykorzystaniem Google Gemini Image. "
    "Wszystkie ograniczenia schematu są egzekwowane na poziomie formularza — "
    "żadnych nieprawidłowych wywołań API."
)


def build_app() -> gr.Blocks:
    with gr.Blocks(title=_TITLE) as app:
        gr.Markdown(f"# {_TITLE}")
        gr.Markdown(_DESCRIPTION)

        # ----------------------------------------------------------------- #
        # API key — entered per user, held in browser session state only.
        # Never written to disk by this app.
        # ----------------------------------------------------------------- #
        with gr.Group(elem_classes=["api-key-row"]):
            with gr.Row():
                with gr.Column(scale=4):
                    api_key_input = gr.Textbox(
                        label="Klucz API Gemini",
                        type="password",
                        placeholder="AIza...   (pobierz z https://aistudio.google.com/app/apikey)",
                        info=(
                            "Wymagany do generowania. Klucz pozostaje wyłącznie w pamięci "
                            "Twojej sesji przeglądarki — nie jest zapisywany ani logowany."
                        ),
                        value=os.environ.get("GEMINI_API_KEY", ""),
                    )
                with gr.Column(scale=1):
                    api_key_status = gr.Markdown(
                        "**Status:** brak klucza" if not os.environ.get("GEMINI_API_KEY")
                        else "**Status:** wykryto klucz w środowisku"
                    )

        def _on_api_key_change(key: str) -> str:
            if not key or not key.strip():
                return "**Status:** brak klucza"
            if not key.strip().startswith("AIza"):
                return "**Status:** klucz wygląda nieprawidłowo (powinien zaczynać się od 'AIza')"
            return f"**Status:** klucz wprowadzony ({len(key.strip())} znaków)"

        api_key_input.change(
            fn=_on_api_key_change,
            inputs=[api_key_input],
            outputs=[api_key_status],
        )

        with gr.Tabs():
            with gr.Tab("1. Generuj wariant"):
                generate.build_tab(api_key_input)

            with gr.Tab("2. Porównaj / Wsadowo"):
                compare.build_tab(api_key_input)

            with gr.Tab("3. Koszty"):
                costs.build_tab()

            with gr.Tab("4. Schemat / Nogi"):
                schemas.build_tab()

    return app


def main() -> None:
    app = build_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        share=False,
        show_error=True,
        quiet=False,
        css=_CSS,
        theme=_THEME,
    )


if __name__ == "__main__":
    main()
