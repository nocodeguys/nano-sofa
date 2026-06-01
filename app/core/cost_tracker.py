"""
cost_tracker.py — Per-request cost calculation and session-level accumulation.

Pricing is sourced from docs/research/nano-banana-state.md (2026-05-08).
All prices are USD. Never hardcode prices in other modules — import from here.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------- #
# Pricing tables (from nano-banana-state.md, 2026-05-08)
# --------------------------------------------------------------------------- #

# Standard (non-batch) output image prices per generated image
OUTPUT_IMAGE_PRICE_STD: dict[str, dict[str, float]] = {
    "gemini-2.5-flash-image": {
        "1K": 0.039,
        "2K": 0.039,   # Flash is capped at 1K; this entry is defensive
        "4K": 0.039,
    },
    "gemini-3.1-flash-image-preview": {
        "1K": 0.067,
        "2K": 0.101,
        "4K": 0.151,
    },
    "gemini-3-pro-image-preview": {
        "1K": 0.134,
        "2K": 0.134,   # Pro pricing covers 1K–2K at same rate
        "4K": 0.240,
    },
}

# Batch (50% off) output image prices
OUTPUT_IMAGE_PRICE_BATCH: dict[str, dict[str, float]] = {
    "gemini-2.5-flash-image": {
        "1K": 0.0195,
        "2K": 0.0195,
        "4K": 0.0195,
    },
    "gemini-3.1-flash-image-preview": {
        "1K": 0.034,
        "2K": 0.050,
        "4K": 0.076,
    },
    "gemini-3-pro-image-preview": {
        "1K": 0.067,
        "2K": 0.067,
        "4K": 0.120,
    },
}

# Input image costs (per reference image)
# gemini-2.5-flash-image: 258 tokens × $0.30/1M = $0.000077/img (post Nov-2025 reduction)
# Preview models: assumed same tier text input rate
INPUT_IMAGE_TOKEN_COST: dict[str, float] = {
    "gemini-2.5-flash-image": 0.000077,   # 258 tok × $0.30/1M
    "gemini-3.1-flash-image-preview": 0.000129,  # 258 tok × $0.50/1M (estimated)
    "gemini-3-pro-image-preview": 0.000516,      # 258 tok × $2.00/1M (estimated)
}

# Thinking token cost (Pro only, per 1M tokens)
THINKING_TOKEN_PRICE_PER_1M: dict[str, float] = {
    "gemini-2.5-flash-image": 0.0,
    "gemini-3.1-flash-image-preview": 3.50,   # approximate — not independently verified
    "gemini-3-pro-image-preview": 12.00,      # from third-party analysis
}

# Estimated thinking tokens for a complex multi-reference sofa prompt
# Simple: ~200 tok, complex multi-ref: ~600 tok
THINKING_TOKEN_ESTIMATE_SIMPLE = 200
THINKING_TOKEN_ESTIMATE_COMPLEX = 600

# Text input prices per 1M tokens
TEXT_INPUT_PRICE_PER_1M: dict[str, float] = {
    "gemini-2.5-flash-image": 0.30,
    "gemini-3.1-flash-image-preview": 0.50,
    "gemini-3-pro-image-preview": 2.00,
}

# Average sofa prompt token count (estimated from schema + system instruction)
PROMPT_TOKEN_ESTIMATE = 800


@dataclass
class CostEstimate:
    """Pre-generation cost projection shown in the UI."""
    model_id: str
    resolution: str
    num_ref_images: int
    is_batch: bool = False
    has_thinking: bool = False
    is_complex_prompt: bool = True

    output_image_cost: float = field(init=False)
    input_image_cost: float = field(init=False)
    text_input_cost: float = field(init=False)
    thinking_cost_low: float = field(init=False)
    thinking_cost_high: float = field(init=False)
    total_low: float = field(init=False)
    total_high: float = field(init=False)

    def __post_init__(self) -> None:
        price_table = OUTPUT_IMAGE_PRICE_BATCH if self.is_batch else OUTPUT_IMAGE_PRICE_STD
        model_prices = price_table.get(self.model_id, {})
        self.output_image_cost = model_prices.get(self.resolution, 0.039)

        per_ref = INPUT_IMAGE_TOKEN_COST.get(self.model_id, 0.000077)
        self.input_image_cost = per_ref * self.num_ref_images

        text_rate = TEXT_INPUT_PRICE_PER_1M.get(self.model_id, 0.30)
        self.text_input_cost = (PROMPT_TOKEN_ESTIMATE / 1_000_000) * text_rate

        thinking_rate = THINKING_TOKEN_PRICE_PER_1M.get(self.model_id, 0.0)
        tok_simple = THINKING_TOKEN_ESTIMATE_SIMPLE
        tok_complex = THINKING_TOKEN_ESTIMATE_COMPLEX
        if self.has_thinking and thinking_rate > 0:
            self.thinking_cost_low = (tok_simple / 1_000_000) * thinking_rate
            self.thinking_cost_high = (tok_complex / 1_000_000) * thinking_rate
        else:
            self.thinking_cost_low = 0.0
            self.thinking_cost_high = 0.0

        base = self.output_image_cost + self.input_image_cost + self.text_input_cost
        self.total_low = base + self.thinking_cost_low
        self.total_high = base + self.thinking_cost_high

    def format_breakdown(self) -> str:
        lines = [
            f"Output image ({self.resolution}): ${self.output_image_cost:.4f}",
            f"Input images ({self.num_ref_images} ref): ${self.input_image_cost:.6f}",
            f"Text input (~{PROMPT_TOKEN_ESTIMATE} tok): ${self.text_input_cost:.6f}",
        ]
        if self.thinking_cost_high > 0:
            lines.append(
                f"Thinking tokens (est.): ${self.thinking_cost_low:.4f} – ${self.thinking_cost_high:.4f}"
            )
        if self.thinking_cost_high > 0:
            lines.append(f"Total estimate: ${self.total_low:.4f} – ${self.total_high:.4f}")
        else:
            lines.append(f"Total estimate: ${self.total_low:.4f}")
        if self.is_batch:
            lines.append("(Batch pricing applied — 50% discount)")
        return "\n".join(lines)

    def format_summary(self) -> str:
        if self.thinking_cost_high > 0:
            return f"~${self.total_low:.4f} – ${self.total_high:.4f} / image"
        return f"~${self.total_low:.4f} / image"


@dataclass
class GenerationRecord:
    """Single generation result for persistence."""
    generation_id: str
    timestamp: float
    model_id: str
    resolution: str
    num_ref_images: int
    actual_cost: float
    status: str   # "success" | "failed" | "retried"
    output_path: Optional[str]
    error_message: Optional[str]
    prompt_summary: str
    leg_id: Optional[str]
    upholstery_color: str
    upholstery_material: str
    camera_angle: str
    turn_number: int = 1
    thinking_tokens_billed: Optional[int] = None
    elapsed_ms: Optional[int] = None   # measured wall-clock of the generate() call


# --------------------------------------------------------------------------- #
# Duration / ETA estimation
# --------------------------------------------------------------------------- #
# Rough per-image wall-clock seeds (seconds) by tier × resolution: (p50, p90).
# p50 = typical, p90 = the "taking longer than usual" threshold. These are
# starting estimates only — measured_eta() refines them from real history once
# enough successful renders accrue.
_DURATION_SEED: dict[str, dict[str, tuple[float, float]]] = {
    "flash": {"1K": (8.0, 16.0),  "2K": (13.0, 26.0), "4K": (20.0, 38.0)},
    "pro":   {"1K": (18.0, 34.0), "2K": (26.0, 50.0), "4K": (40.0, 72.0)},
}


def estimate_duration(model_id: str, resolution: str, num_ref_images: int = 0) -> dict:
    """Static ETA seed for a single render. Returns {p50_s, p90_s, source, n}."""
    tier = "pro" if "pro" in (model_id or "") else "flash"
    res = (resolution or "1K").upper()
    if res not in ("1K", "2K", "4K"):
        res = "1K"
    p50, p90 = _DURATION_SEED[tier].get(res, _DURATION_SEED[tier]["1K"])
    p50 += 1.2 * max(0, num_ref_images)   # each extra reference adds a little
    p90 += 2.0 * max(0, num_ref_images)
    return {"p50_s": round(p50, 1), "p90_s": round(p90, 1), "source": "estimate", "n": 0}


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def measured_eta(model_id: str, resolution: str, limit: int = 80, min_samples: int = 4) -> Optional[dict]:
    """Measured p50/p90 (seconds) from recent successful renders of this exact
    model+resolution, or None if there isn't enough history yet."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT elapsed_ms FROM generations WHERE model_id = ? AND resolution = ? "
            "AND status = 'success' AND elapsed_ms IS NOT NULL "
            "ORDER BY timestamp DESC LIMIT ?",
            (model_id, resolution, limit),
        ).fetchall()
    except Exception:
        return None
    finally:
        conn.close()
    vals = sorted(float(r["elapsed_ms"]) / 1000.0 for r in rows if r["elapsed_ms"])
    if len(vals) < min_samples:
        return None
    return {
        "p50_s": round(_percentile(vals, 50), 1),
        "p90_s": round(_percentile(vals, 90), 1),
        "source": "measured",
        "n": len(vals),
    }


def eta_for(model_id: str, resolution: str, num_ref_images: int = 0) -> dict:
    """Best available ETA: measured history if we have enough samples, else the
    static seed. Always returns {p50_s, p90_s, source, n}."""
    return measured_eta(model_id, resolution) or estimate_duration(model_id, resolution, num_ref_images)


def estimate_cost(
    model_id: str,
    resolution: str,
    num_ref_images: int,
    is_batch: bool = False,
) -> CostEstimate:
    from app.core.schema_loader import schema

    has_thinking = schema.thinking_on_by_default(model_id)
    return CostEstimate(
        model_id=model_id,
        resolution=resolution,
        num_ref_images=num_ref_images,
        is_batch=is_batch,
        has_thinking=has_thinking,
    )


def estimate_batch_cost(
    model_id: str,
    resolution: str,
    num_ref_images: int,
    count: int,
) -> tuple[CostEstimate, float, float]:
    """
    Returns (per_image_estimate, total_low, total_high) for a batch of `count`
    images.
    """
    est = estimate_cost(model_id, resolution, num_ref_images, is_batch=False)
    return est, est.total_low * count, est.total_high * count


# --------------------------------------------------------------------------- #
# SQLite persistence
# --------------------------------------------------------------------------- #

_DB_PATH = Path(__file__).resolve().parents[1] / "state" / "costs.db"


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS generations (
            generation_id   TEXT PRIMARY KEY,
            timestamp       REAL NOT NULL,
            model_id        TEXT NOT NULL,
            resolution      TEXT NOT NULL,
            num_ref_images  INTEGER NOT NULL,
            actual_cost     REAL NOT NULL,
            status          TEXT NOT NULL,
            output_path     TEXT,
            error_message   TEXT,
            prompt_summary  TEXT,
            leg_id          TEXT,
            upholstery_color    TEXT,
            upholstery_material TEXT,
            camera_angle    TEXT,
            turn_number     INTEGER DEFAULT 1,
            thinking_tokens_billed INTEGER
        )
        """
    )
    # Additive migration: add elapsed_ms to pre-existing DBs (CREATE TABLE IF
    # NOT EXISTS won't add new columns to a table that already exists).
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(generations)").fetchall()}
    if "elapsed_ms" not in cols:
        conn.execute("ALTER TABLE generations ADD COLUMN elapsed_ms INTEGER")
    conn.commit()


def record_generation(rec: GenerationRecord) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO generations (
                generation_id, timestamp, model_id, resolution,
                num_ref_images, actual_cost, status, output_path,
                error_message, prompt_summary, leg_id,
                upholstery_color, upholstery_material, camera_angle,
                turn_number, thinking_tokens_billed, elapsed_ms
            ) VALUES (
                :generation_id, :timestamp, :model_id, :resolution,
                :num_ref_images, :actual_cost, :status, :output_path,
                :error_message, :prompt_summary, :leg_id,
                :upholstery_color, :upholstery_material, :camera_angle,
                :turn_number, :thinking_tokens_billed, :elapsed_ms
            )
            """,
            {
                "generation_id": rec.generation_id,
                "timestamp": rec.timestamp,
                "model_id": rec.model_id,
                "resolution": rec.resolution,
                "num_ref_images": rec.num_ref_images,
                "actual_cost": rec.actual_cost,
                "status": rec.status,
                "output_path": rec.output_path,
                "error_message": rec.error_message,
                "prompt_summary": rec.prompt_summary,
                "leg_id": rec.leg_id,
                "upholstery_color": rec.upholstery_color,
                "upholstery_material": rec.upholstery_material,
                "camera_angle": rec.camera_angle,
                "turn_number": rec.turn_number,
                "thinking_tokens_billed": rec.thinking_tokens_billed,
                "elapsed_ms": rec.elapsed_ms,
            },
        )
        conn.commit()
    finally:
        conn.close()


def session_total() -> float:
    """Sum of all actual_cost values in the DB (whole-session running total)."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(actual_cost), 0.0) as total FROM generations WHERE status = 'success'"
        ).fetchone()
        return float(row["total"])
    finally:
        conn.close()


def recent_generations(limit: int = 50) -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT * FROM generations
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def model_cost_summary() -> list[dict]:
    """Per-model cost and count summary."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT
                model_id,
                COUNT(*) as count,
                SUM(actual_cost) as total_cost,
                AVG(actual_cost) as avg_cost
            FROM generations
            WHERE status = 'success'
            GROUP BY model_id
            ORDER BY total_cost DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def new_generation_id() -> str:
    return str(uuid.uuid4())
