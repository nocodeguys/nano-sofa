"""
costs.py — Tab 3: Cost Tracking

Shows per-request costs, session totals, per-model breakdowns, and
full generation history from the SQLite cost DB.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import gradio as gr

from app.core.cost_tracker import (
    OUTPUT_IMAGE_PRICE_STD,
    OUTPUT_IMAGE_PRICE_BATCH,
    INPUT_IMAGE_TOKEN_COST,
    THINKING_TOKEN_PRICE_PER_1M,
    TEXT_INPUT_PRICE_PER_1M,
    model_cost_summary,
    recent_generations,
    session_total,
)
from app.core.schema_loader import schema


def _format_ts(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


def _session_summary_md() -> str:
    total = session_total()
    summary_rows = model_cost_summary()

    lines = [
        f"## Session Total: ${total:.4f}",
        "",
        "### Per-model breakdown",
        "",
        "| Model | Generations | Total cost | Avg / image |",
        "|---|---|---|---|",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['model_id']} | {row['count']} | ${row['total_cost']:.4f} | ${row['avg_cost']:.4f} |"
        )
    if not summary_rows:
        lines.append("| — | 0 | $0.0000 | — |")

    return "\n".join(lines)


def _pricing_reference_md() -> str:
    lines = [
        "## Pricing Reference (from nano-banana-state.md, 2026-05-08)",
        "",
        "### Output image prices — standard (per image)",
        "",
        "| Model | 1K | 2K | 4K |",
        "|---|---|---|---|",
    ]
    for model_id in schema.model_ids:
        std = OUTPUT_IMAGE_PRICE_STD.get(model_id, {})
        lines.append(
            f"| {model_id} | ${std.get('1K', 0):.4f} | ${std.get('2K', 0):.4f} | ${std.get('4K', 0):.4f} |"
        )

    lines += [
        "",
        "### Output image prices — batch (50% off)",
        "",
        "| Model | 1K | 2K | 4K |",
        "|---|---|---|---|",
    ]
    for model_id in schema.model_ids:
        batch = OUTPUT_IMAGE_PRICE_BATCH.get(model_id, {})
        lines.append(
            f"| {model_id} | ${batch.get('1K', 0):.4f} | ${batch.get('2K', 0):.4f} | ${batch.get('4K', 0):.4f} |"
        )

    lines += [
        "",
        "### Other costs",
        "",
        "| Model | Input image / ref | Text input / 1M tok | Thinking / 1M tok |",
        "|---|---|---|---|",
    ]
    for model_id in schema.model_ids:
        img_cost = INPUT_IMAGE_TOKEN_COST.get(model_id, 0)
        text_rate = TEXT_INPUT_PRICE_PER_1M.get(model_id, 0)
        think_rate = THINKING_TOKEN_PRICE_PER_1M.get(model_id, 0)
        think_str = f"${think_rate:.2f}" if think_rate > 0 else "N/A"
        lines.append(
            f"| {model_id} | ${img_cost:.6f} | ${text_rate:.2f} | {think_str} |"
        )

    lines += [
        "",
        "### Known cost quirks",
        "",
        "- **gemini-2.5-flash-image:** Input image cost reduced from $0.001290 to $0.000077 per ref on 2025-11-04 "
        "(258 tokens × $0.30/1M). Three refs add ~$0.00023 — negligible.",
        "- **gemini-3-pro-image-preview:** Thinking tokens cannot be disabled and are billed even on failed "
        "safety-check generations ($0.002–$0.006 per failed attempt).",
        "- **gemini-3.1-flash-image-preview:** Thinking on by default; adds latency and tokens on complex prompts.",
        "- **gemini-2.5-flash-image:** Scheduled for deprecation 2026-10-02. Migration path: gemini-3.1-flash-image-preview.",
    ]

    return "\n".join(lines)


def _history_table(limit: int = 100) -> list[list[Any]]:
    records = recent_generations(limit=limit)
    rows = []
    for rec in records:
        rows.append(
            [
                _format_ts(rec.get("timestamp", 0)),
                rec.get("model_id", ""),
                rec.get("resolution", ""),
                rec.get("upholstery_color", ""),
                rec.get("upholstery_material", ""),
                rec.get("leg_id", ""),
                rec.get("camera_angle", ""),
                rec.get("status", ""),
                f"${rec.get('actual_cost', 0):.4f}",
                rec.get("turn_number", 1),
                rec.get("generation_id", "")[:8],
            ]
        )
    return rows


_HISTORY_HEADERS = [
    "Time",
    "Model",
    "Resolution",
    "Color",
    "Material",
    "Leg",
    "Angle",
    "Status",
    "Cost",
    "Turn",
    "ID (short)",
]


def build_tab() -> None:
    """Build the Cost Tracking tab. Called inside a gr.Tab() context."""

    with gr.Row():
        refresh_btn = gr.Button("Refresh all", variant="secondary")
        session_total_md = gr.Markdown(f"**Session total:** ${session_total():.4f}")

    # ------------------------------------------------------------------ #
    # Session summary
    # ------------------------------------------------------------------ #
    summary_md = gr.Markdown(_session_summary_md())

    gr.Markdown("---")

    # ------------------------------------------------------------------ #
    # Pricing reference
    # ------------------------------------------------------------------ #
    with gr.Accordion("Pricing reference (from research doc)", open=False):
        pricing_md = gr.Markdown(_pricing_reference_md())

    gr.Markdown("---")

    # ------------------------------------------------------------------ #
    # Generation history
    # ------------------------------------------------------------------ #
    gr.Markdown("## Generation History")
    history_limit = gr.Slider(
        minimum=10,
        maximum=500,
        value=100,
        step=10,
        label="Number of recent records to show",
    )
    history_table = gr.Dataframe(
        value=_history_table(100),
        headers=_HISTORY_HEADERS,
        datatype=["str"] * len(_HISTORY_HEADERS),
        interactive=False,
        wrap=False,
    )

    # ------------------------------------------------------------------ #
    # Failure analysis
    # ------------------------------------------------------------------ #
    gr.Markdown("---")
    gr.Markdown("## Failure Analysis")
    failure_md = gr.Markdown(_build_failure_md())

    # ------------------------------------------------------------------ #
    # Event wiring
    # ------------------------------------------------------------------ #

    def _refresh_all(limit):
        return (
            f"**Session total:** ${session_total():.4f}",
            _session_summary_md(),
            _history_table(int(limit)),
            _build_failure_md(),
        )

    refresh_btn.click(
        fn=_refresh_all,
        inputs=[history_limit],
        outputs=[session_total_md, summary_md, history_table, failure_md],
    )

    history_limit.change(
        fn=lambda lim: _history_table(int(lim)),
        inputs=[history_limit],
        outputs=[history_table],
    )


def _build_failure_md() -> str:
    records = recent_generations(limit=500)
    failed = [r for r in records if r.get("status") == "failed"]
    total = len(records)
    n_failed = len(failed)
    success_rate = (
        f"{((total - n_failed) / total * 100):.1f}%" if total > 0 else "N/A"
    )

    lines = [
        f"**Total generations:** {total}  |  "
        f"**Failed:** {n_failed}  |  "
        f"**Success rate:** {success_rate}",
        "",
    ]

    if failed:
        lines.append("### Recent failures")
        lines.append("")
        lines.append("| Time | Model | Error |")
        lines.append("|---|---|---|")
        for rec in failed[:20]:
            ts = _format_ts(rec.get("timestamp", 0))
            model = rec.get("model_id", "")
            err = (rec.get("error_message") or "unknown")[:80].replace("|", "/")
            lines.append(f"| {ts} | {model} | {err} |")
    else:
        lines.append("No failures recorded.")

    lines += [
        "",
        "### Known failure rates (from research)",
        "",
        "- gemini-2.5-flash-image: ~30% failure during 9 AM–5 PM Pacific peak hours",
        "- gemini-3-pro-image-preview: ~45% failure during peak hours",
        "- gemini-3.1-flash-image-preview: between the two (not separately documented)",
        "",
        "The generator retries up to 4 times with exponential backoff. "
        "A 'failed' record means all retry attempts were exhausted.",
    ]

    return "\n".join(lines)
