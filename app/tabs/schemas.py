"""
schemas.py — Tab 4: Schema & Leg Library Viewer

Read-only browse of:
- Active sofa.json schema with rendered field docs
- Leg manifest entries with explicit descriptors
- Test matrix doc
- Change request textarea (writes to prompts/change-requests/)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import gradio as gr

from app.core.leg_browser import leg_browser, reload as reload_legs
from app.core.schema_loader import schema, reload as reload_schema

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = _REPO_ROOT / "prompts" / "schemas" / "sofa.json"
_RATIONALE_PATH = _REPO_ROOT / "prompts" / "schemas" / "sofa.md"
_TEST_MATRIX_PATH = _REPO_ROOT / "prompts" / "test-matrices" / "sofa.md"
_CHANGE_REQUESTS_DIR = _REPO_ROOT / "prompts" / "change-requests"
_RESEARCH_PATH = _REPO_ROOT / "docs" / "research" / "nano-banana-state.md"


def _read_file_md(path: Path) -> str:
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except Exception as exc:
            return f"*Could not read {path.name}: {exc}*"
    return f"*File not found: {path}*"


def _schema_fields_md() -> str:
    """Render schema field docs as markdown."""
    lines = [
        f"# Sofa schema v{schema._raw.get('version', '?')}",
        "",
        "Field reference generated from `prompts/schemas/sofa.json`.",
        "",
        "---",
        "",
        "## Model",
        "",
        f"**Allowed values:** {', '.join(f'`{m}`' for m in schema.model_ids)}",
        "",
        "### Per-model constraints",
        "",
        "| Model | Max refs | Max resolution | Resolution param | Thinking | Deprecation |",
        "|---|---|---|---|---|---|",
    ]
    for model_id in schema.model_ids:
        mc = schema.model_constraints.get(model_id, {})
        lines.append(
            f"| `{model_id}` | "
            f"{mc.get('max_reference_images', '?')} | "
            f"{mc.get('max_output_resolution', '?')} | "
            f"{'yes' if mc.get('supports_resolution_param') else 'no'} | "
            f"{'on by default' if mc.get('thinking_on_by_default') else 'no'} | "
            f"{mc.get('deprecation_date') or 'not set'} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Reference slots",
        "",
        "Slot order is declared and must be preserved. The model uses positional context.",
        "",
        "| Slot | Key | Description |",
        "|---|---|---|",
    ]
    for i, slot_key in enumerate(schema.reference_slot_names, start=1):
        desc = schema.reference_slot_descriptions.get(slot_key, "")
        lines.append(f"| {i} | `{slot_key}` | {desc[:120]}... |")

    lines += [
        "",
        "---",
        "",
        "## Product",
        "",
        f"**Configurations:** {', '.join(schema.sofa_configurations)}",
        f"**Leg count:** {schema.leg_count_min}–{schema.leg_count_max}",
        "",
        "**Preserve options:**",
        "",
    ]
    for p in schema.preserve_options:
        lines.append(f"- `{p}`")

    lines += [
        "",
        "---",
        "",
        "## Upholstery materials",
        "",
        ", ".join(f"`{m}`" for m in schema.material_options),
        "",
        "---",
        "",
        "## Camera angles",
        "",
        "| Enum | Degrees from left |",
        "|---|---|",
    ]
    for angle, deg in schema.angle_to_degrees.items():
        lines.append(f"| `{angle}` | {deg}° |")

    lines += [
        "",
        "---",
        "",
        "## Output",
        "",
        f"**Aspect ratios:** {', '.join(schema.aspect_ratio_options)}",
        f"**Resolutions:** {', '.join(schema.resolution_options)} (model-dependent ceiling)",
        f"**Default resolution:** `{schema.resolution_default}`",
        "",
        "---",
        "",
        "## Default negative list",
        "",
    ]
    for item in schema.negative_defaults:
        lines.append(f"- {item}")

    return "\n".join(lines)


def _leg_manifest_md() -> str:
    lines = [
        f"# Leg manifest v{leg_browser.schema_version}",
        f"**{len(leg_browser.entries)} entries across {len(leg_browser.style_families())} style families**",
        "",
        "---",
        "",
    ]
    for style in leg_browser.style_families():
        lines.append(f"## {style.capitalize()} style")
        lines.append("")
        for entry in leg_browser.by_style(style):
            lines.append(f"### `{entry.id}`")
            lines.append(f"**Material:** {entry.material}")
            lines.append(f"**Tags:** {', '.join(entry.tags)}")
            lines.append(f"**Shadow hint:** {entry.shadow_direction_hint}")
            lines.append(f"**License:** {entry.license}")
            lines.append("")
            lines.append(f"**Explicit descriptor:**")
            lines.append(f"> {entry.explicit_descriptor}")
            lines.append("")
            geom = entry.geometry
            if geom:
                lines.append(f"**Geometry:** profile={geom.get('profile', '?')}, "
                              f"height={geom.get('default_height_cm', '?')} cm, "
                              f"braces={geom.get('has_braces', False)}, "
                              f"brackets={geom.get('has_brackets', False)}")
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def build_tab() -> None:
    """Build the Schema Viewer tab. Called inside a gr.Tab() context."""

    with gr.Row():
        reload_btn = gr.Button("Reload from disk", variant="secondary")
        reload_status = gr.Markdown("")

    with gr.Tabs():
        with gr.Tab("Schema fields"):
            schema_fields_md = gr.Markdown(_schema_fields_md())

        with gr.Tab("Schema rationale"):
            rationale_md = gr.Markdown(_read_file_md(_RATIONALE_PATH))

        with gr.Tab("Test matrix"):
            test_matrix_md = gr.Markdown(_read_file_md(_TEST_MATRIX_PATH))

        with gr.Tab("Leg manifest"):
            leg_manifest_md = gr.Markdown(_leg_manifest_md())

        with gr.Tab("Research notes"):
            research_md = gr.Markdown(_read_file_md(_RESEARCH_PATH))

        with gr.Tab("Raw sofa.json"):
            with open(_SCHEMA_PATH) as fh:
                raw_json = json.dumps(json.load(fh), indent=2)
            schema_json_display = gr.Code(
                value=raw_json,
                language="json",
                label="prompts/schemas/sofa.json (read-only)",
                interactive=False,
            )

    gr.Markdown("---")

    # ------------------------------------------------------------------ #
    # Change request
    # ------------------------------------------------------------------ #
    gr.Markdown("## Request Schema Changes")
    gr.Markdown(
        "Write a change request for the furniture-prompt-architect agent. "
        "Saved to `prompts/change-requests/` as a markdown file."
    )

    change_request_title = gr.Textbox(
        label="Request title (short, used as filename)",
        placeholder="e.g. add fabric-pattern variant axis",
    )
    change_request_text = gr.Textbox(
        label="Change request detail",
        lines=8,
        placeholder=(
            "Describe the schema change needed, why it is needed, "
            "and which failure mode or workflow gap it addresses."
        ),
    )
    submit_change_request_btn = gr.Button("Save change request", variant="secondary")
    change_request_status = gr.Markdown("")

    # ------------------------------------------------------------------ #
    # Event wiring
    # ------------------------------------------------------------------ #

    def _reload_all():
        reload_schema()
        reload_legs()
        return (
            "Reloaded from disk.",
            _schema_fields_md(),
            _read_file_md(_RATIONALE_PATH),
            _read_file_md(_TEST_MATRIX_PATH),
            _leg_manifest_md(),
            _read_file_md(_RESEARCH_PATH),
        )

    reload_btn.click(
        fn=_reload_all,
        inputs=[],
        outputs=[
            reload_status,
            schema_fields_md,
            rationale_md,
            test_matrix_md,
            leg_manifest_md,
            research_md,
        ],
    )

    def _save_change_request(title: str, text: str) -> str:
        if not title.strip():
            return "**Error:** Provide a title before saving."
        if not text.strip():
            return "**Error:** Change request body is empty."

        _CHANGE_REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
        safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title).strip()
        safe_title = safe_title.replace(" ", "-").lower()
        ts = int(time.time())
        filename = f"{ts}-{safe_title}.md"
        path = _CHANGE_REQUESTS_DIR / filename

        content = f"# Change request: {title}\n\nCreated: {time.strftime('%Y-%m-%d %H:%M')}\n\n---\n\n{text}\n"
        path.write_text(content, encoding="utf-8")
        return f"Saved to `{path.relative_to(_REPO_ROOT)}`"

    submit_change_request_btn.click(
        fn=_save_change_request,
        inputs=[change_request_title, change_request_text],
        outputs=[change_request_status],
    )
