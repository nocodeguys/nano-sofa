"""
compare.py — Tab 2: Comparison Gallery

Side-by-side variant review with batch queue support. Loads previously
generated images from the outputs directory and the cost DB. Allows queuing
multiple variants for batch generation.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Optional

import gradio as gr
from PIL import Image

from app.core.cost_tracker import estimate_batch_cost, recent_generations, session_total
from app.core.generator import GenerationRequest, GenerationResult, generate, validate_request
from app.core.leg_browser import leg_browser
from app.core.schema_loader import schema

_OUTPUTS_DIR = Path(__file__).resolve().parents[1] / "outputs"

# In-process batch queue state (thread-safe via lock)
_batch_lock = threading.Lock()
_batch_queue: list[dict] = []
_batch_results: list[dict] = []
_batch_running = False


def _load_recent_images(limit: int = 12) -> list[tuple[Optional[Image.Image], str]]:
    """
    Returns list of (PIL image or None, caption) for recent successful generations.
    """
    records = recent_generations(limit=limit)
    out: list[tuple[Optional[Image.Image], str]] = []
    for rec in records:
        if rec.get("status") != "success":
            continue
        path_str = rec.get("output_path")
        if not path_str:
            continue
        p = Path(path_str)
        caption = (
            f"{rec.get('upholstery_color', '')} {rec.get('upholstery_material', '')} / "
            f"{rec.get('leg_id', 'existing')} / "
            f"{rec.get('camera_angle', '')} / "
            f"{rec.get('model_id', '').split('-')[0]} {rec.get('resolution', '')}"
        )
        if p.exists():
            try:
                img = Image.open(str(p))
                out.append((img, caption))
            except Exception:
                out.append((None, caption + " [load error]"))
        else:
            out.append((None, caption + " [file missing]"))
    return out


def _queue_status_md() -> str:
    with _batch_lock:
        total = len(_batch_queue)
        done = len(_batch_results)
        running = "running" if _batch_running else "idle"
        pending = total - done
    if total == 0:
        return "Batch queue: empty"
    success = sum(1 for r in _batch_results if r.get("success"))
    failed = done - success
    return (
        f"**Batch queue:** {total} total | "
        f"{pending} pending | {done} done ({success} ok, {failed} failed) | "
        f"Status: {running}"
    )


def _build_batch_variant(
    model_id: str,
    base_product_image,
    sofa_configuration: str,
    leg_count: int,
    preserve_list: list[str],
    system_instruction: str,
    camera_angle: str,
    shadow_direction: str,
    aspect_ratio: str,
    resolution: str,
    output_style: str,
    negative_text: str,
    # Variant axis values
    upholstery_color: str,
    upholstery_material: str,
    leg_label: str,
) -> GenerationRequest:
    leg_id: Optional[str] = None
    leg_render_path: Optional[Path] = None
    leg_descriptor = ""

    if leg_label and leg_label != "None — keep existing legs":
        leg_id = leg_browser.id_from_label(leg_label)
        if leg_id:
            leg_render_path = leg_browser.render_path_for(leg_id, camera_angle)
            leg_descriptor = leg_browser.explicit_descriptor_for(leg_id)

    angle_degrees = schema.angle_to_degrees.get(camera_angle, 35)
    neg_items = [ln.strip() for ln in negative_text.splitlines() if ln.strip()]

    return GenerationRequest(
        model_id=model_id,
        base_product_image=base_product_image,
        leg_reference_image=leg_render_path,
        sofa_configuration=sofa_configuration,
        leg_count=leg_count,
        preserve_list=preserve_list,
        upholstery_color=upholstery_color,
        upholstery_material=upholstery_material,
        leg_id=leg_id,
        leg_explicit_descriptor=leg_descriptor,
        camera_angle=camera_angle,
        angle_degrees_from_left=angle_degrees,
        shadow_direction=shadow_direction,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        output_style=output_style,
        system_instruction=system_instruction,
        negative_list=neg_items,
    )


def _run_batch_worker() -> None:
    global _batch_running
    with _batch_lock:
        _batch_running = True
        queue_copy = list(_batch_queue)

    for i, item in enumerate(queue_copy):
        req: GenerationRequest = item["request"]
        try:
            result = generate(req)
            with _batch_lock:
                _batch_results.append(
                    {
                        "index": i,
                        "success": result.success,
                        "output_path": str(result.output_path) if result.output_path else None,
                        "actual_cost": result.actual_cost,
                        "error": result.error_message,
                        "label": item.get("label", f"variant-{i+1}"),
                    }
                )
        except Exception as exc:
            with _batch_lock:
                _batch_results.append(
                    {
                        "index": i,
                        "success": False,
                        "output_path": None,
                        "actual_cost": 0.0,
                        "error": str(exc),
                        "label": item.get("label", f"variant-{i+1}"),
                    }
                )

    with _batch_lock:
        _batch_running = False


def _queue_batch(requests: list[tuple[GenerationRequest, str]]) -> str:
    global _batch_queue, _batch_results
    with _batch_lock:
        _batch_queue = [{"request": req, "label": label} for req, label in requests]
        _batch_results = []

    t = threading.Thread(target=_run_batch_worker, daemon=True)
    t.start()
    return _queue_status_md()


def _get_batch_gallery() -> list[tuple[Optional[Image.Image], str]]:
    with _batch_lock:
        results = list(_batch_results)

    out: list[tuple[Optional[Image.Image], str]] = []
    for r in results:
        label = r.get("label", "variant")
        path_str = r.get("output_path")
        if path_str and Path(path_str).exists():
            try:
                img = Image.open(path_str)
                out.append((img, f"{label} — ${r['actual_cost']:.4f}"))
            except Exception:
                out.append((None, f"{label} — load error"))
        else:
            err = r.get("error", "unknown error")
            out.append((None, f"{label} — FAILED: {err[:60]}"))
    return out


def build_tab(api_key_input=None) -> None:
    """Build the Comparison Gallery tab.

    `api_key_input` is the shared password Textbox from main.py — its current
    value is injected into every queued request so the batch worker authenticates
    with the user's key (no env var required).
    """

    gr.Markdown(
        "Porównuj warianty obok siebie. Użyj kolejki wsadowej, aby wygenerować "
        "wiele kombinacji i przejrzeć wyniki razem."
    )

    # ------------------------------------------------------------------ #
    # Recent library
    # ------------------------------------------------------------------ #
    with gr.Accordion("Recent generations library", open=True):
        refresh_library_btn = gr.Button("Refresh library", variant="secondary")
        library_gallery = gr.Gallery(
            label="Recent successful generations",
            columns=4,
            height=320,
            allow_preview=True,
            preview=True,
            object_fit="contain",
        )

    gr.Markdown("---")

    # ------------------------------------------------------------------ #
    # Batch builder
    # ------------------------------------------------------------------ #
    gr.Markdown("## Batch Variant Builder")
    gr.Markdown(
        "Set shared parameters below, then define variant axes. "
        "Each axis combination becomes one generation job."
    )

    with gr.Row():
        with gr.Column():
            gr.Markdown("### Shared parameters")
            batch_model = gr.Dropdown(
                choices=schema.model_ids,
                value=schema.model_ids[0],
                label="Model (shared)",
            )
            batch_base_image = gr.Image(
                label="Base product image (shared)",
                type="pil",
                sources=["upload"],
                height=220,
            )
            batch_config = gr.Dropdown(
                choices=schema.sofa_configurations,
                value="3-seater",
                label="Configuration (shared)",
            )
            batch_leg_count = gr.Slider(minimum=2, maximum=12, value=4, step=1, label="Leg count (shared)")
            batch_camera_angle = gr.Dropdown(
                choices=schema.angle_options,
                value="front-34-left",
                label="Camera angle (shared)",
            )
            batch_shadow_direction = gr.Textbox(
                label="Shadow direction (shared)",
                value="4 o-clock",
            )
            batch_aspect_ratio = gr.Dropdown(
                choices=schema.aspect_ratio_options,
                value="4:3",
                label="Aspect ratio (shared)",
            )
            batch_resolution = gr.Dropdown(
                choices=["1K"],
                value="1K",
                label="Resolution (shared — updates with model)",
            )
            batch_output_style = gr.Textbox(
                label="Output style (shared)",
                value=schema.style_default,
                lines=2,
            )
            batch_system_instruction = gr.Textbox(
                label="System instruction (shared)",
                value=schema.system_instruction_default,
                lines=3,
            )
            batch_negative_text = gr.Textbox(
                label="Negative list (shared, one per line)",
                value="\n".join(schema.negative_defaults),
                lines=5,
            )
            batch_preserve_list = gr.CheckboxGroup(
                choices=schema.preserve_options,
                value=[
                    "frame_geometry",
                    "cushion_count_and_arrangement",
                    "stitching_pattern",
                    "camera_angle",
                    "perspective",
                    "leg_count_and_positions",
                ],
                label="Preserve list (shared)",
            )

        with gr.Column():
            gr.Markdown("### Variant axes")
            gr.Markdown(
                "Add comma-separated values for each axis. "
                "All combinations will be queued. "
                "Example: 3 colors × 2 leg styles = 6 jobs."
            )

            batch_colors = gr.Textbox(
                label="Upholstery colors (comma-separated)",
                value="sage green, charcoal, ivory",
                placeholder="sage green, charcoal, ivory, navy",
            )
            batch_materials = gr.Dropdown(
                choices=schema.material_options,
                value=["bouclé"],
                multiselect=True,
                label="Materials (multi-select)",
            )
            batch_legs = gr.Dropdown(
                choices=["None — keep existing legs"]
                + [e.display_label for e in leg_browser.entries.values()],
                value=["None — keep existing legs"],
                multiselect=True,
                label="Leg styles (multi-select)",
            )

            # Cost preview
            batch_cost_preview = gr.Markdown("Select variants to preview batch cost")

            def _update_batch_cost(model_id, colors_str, materials, legs, leg_count):
                colors = [c.strip() for c in colors_str.split(",") if c.strip()]
                count = len(colors) * max(len(materials), 1) * max(len(legs), 1)
                num_refs = 2 if any(l != "None — keep existing legs" for l in legs) else 1
                res = "1K"
                est, total_low, total_high = estimate_batch_cost(model_id, res, num_refs, count)
                return (
                    f"**Batch: {count} generations**\n\n"
                    f"Per image: {est.format_summary()}\n\n"
                    f"Batch total estimate: ${total_low:.3f} – ${total_high:.3f}\n\n"
                    f"Session total so far: ${session_total():.4f}"
                )

            for trigger in [batch_model, batch_colors, batch_materials, batch_legs, batch_leg_count]:
                trigger.change(
                    fn=_update_batch_cost,
                    inputs=[batch_model, batch_colors, batch_materials, batch_legs, batch_leg_count],
                    outputs=[batch_cost_preview],
                )

            queue_batch_btn = gr.Button("Queue batch", variant="primary")
            clear_batch_btn = gr.Button("Clear queue", variant="secondary")

    # ------------------------------------------------------------------ #
    # Queue status and results
    # ------------------------------------------------------------------ #
    gr.Markdown("---")
    batch_status_md = gr.Markdown(_queue_status_md())
    refresh_batch_btn = gr.Button("Refresh batch results", variant="secondary")

    batch_gallery = gr.Gallery(
        label="Batch results",
        columns=4,
        height=400,
        allow_preview=True,
        preview=True,
        object_fit="contain",
    )

    # ------------------------------------------------------------------ #
    # Side-by-side comparison picker
    # ------------------------------------------------------------------ #
    gr.Markdown("---")
    gr.Markdown("## Side-by-Side Comparison")

    with gr.Row():
        compare_left = gr.Image(
            label="Left — upload or select from library",
            type="pil",
            sources=["upload"],
            height=400,
        )
        compare_right = gr.Image(
            label="Right — upload or select from library",
            type="pil",
            sources=["upload"],
            height=400,
        )

    with gr.Row():
        compare_left_caption = gr.Textbox(label="Left caption", interactive=True)
        compare_right_caption = gr.Textbox(label="Right caption", interactive=True)

    # ------------------------------------------------------------------ #
    # Event wiring
    # ------------------------------------------------------------------ #

    # Library refresh
    def _refresh_library():
        items = _load_recent_images(limit=16)
        gallery_data = [(img, cap) for img, cap in items if img is not None]
        return gr.update(value=gallery_data)

    refresh_library_btn.click(
        fn=_refresh_library,
        inputs=[],
        outputs=[library_gallery],
    )

    # Initial library load
    library_gallery.value = _refresh_library()

    # Model change → update resolution choices
    def _batch_model_update(model_id):
        res_choices = schema.resolution_choices_for_model(model_id)
        return gr.update(choices=res_choices, value=res_choices[0])

    batch_model.change(
        fn=_batch_model_update,
        inputs=[batch_model],
        outputs=[batch_resolution],
    )

    # Queue batch
    def _on_queue_batch(
        api_key,
        model_id,
        base_image,
        config,
        leg_count,
        camera_angle,
        shadow_dir,
        aspect_ratio,
        resolution,
        output_style,
        system_instruction,
        negative_text,
        preserve_list,
        colors_str,
        materials,
        legs,
    ):
        if base_image is None:
            return "**Błąd:** Najpierw wgraj zdjęcie produktu.", gr.update()
        if not (api_key or "").strip():
            return (
                "**Błąd:** Wpisz klucz API w polu na górze strony przed kolejkowaniem wsadu.",
                gr.update(),
            )

        colors = [c.strip() for c in colors_str.split(",") if c.strip()]
        if not colors:
            colors = [""]
        if not materials:
            materials = ["bouclé"]
        if not legs:
            legs = ["None — keep existing legs"]

        requests: list[tuple[GenerationRequest, str]] = []
        for color in colors:
            for material in materials:
                for leg_label in legs:
                    req = _build_batch_variant(
                        model_id=model_id,
                        base_product_image=base_image,
                        sofa_configuration=config,
                        leg_count=leg_count,
                        preserve_list=preserve_list,
                        system_instruction=system_instruction,
                        camera_angle=camera_angle,
                        shadow_direction=shadow_dir,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                        output_style=output_style,
                        negative_text=negative_text,
                        upholstery_color=color,
                        upholstery_material=material,
                        leg_label=leg_label,
                    )
                    # Inject the user's API key so the batch worker can authenticate.
                    req.api_key = api_key or ""
                    label = f"{color} {material} / {leg_label.split('—')[0].strip()}"
                    requests.append((req, label))

        status = _queue_batch(requests)
        return status, gr.update()

    queue_batch_btn.click(
        fn=_on_queue_batch,
        inputs=[
            api_key_input,
            batch_model,
            batch_base_image,
            batch_config,
            batch_leg_count,
            batch_camera_angle,
            batch_shadow_direction,
            batch_aspect_ratio,
            batch_resolution,
            batch_output_style,
            batch_system_instruction,
            batch_negative_text,
            batch_preserve_list,
            batch_colors,
            batch_materials,
            batch_legs,
        ],
        outputs=[batch_status_md, batch_gallery],
    )

    # Clear queue
    def _on_clear_batch():
        global _batch_queue, _batch_results
        with _batch_lock:
            _batch_queue = []
            _batch_results = []
        return _queue_status_md(), []

    clear_batch_btn.click(
        fn=_on_clear_batch,
        inputs=[],
        outputs=[batch_status_md, batch_gallery],
    )

    # Refresh batch results
    def _on_refresh_batch():
        status = _queue_status_md()
        gallery_items = _get_batch_gallery()
        gallery_data = [(img, cap) for img, cap in gallery_items if img is not None]
        return status, gr.update(value=gallery_data)

    refresh_batch_btn.click(
        fn=_on_refresh_batch,
        inputs=[],
        outputs=[batch_status_md, batch_gallery],
    )
