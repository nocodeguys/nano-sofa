"""Structured error responses shared by the API routers."""

from __future__ import annotations

from fastapi.responses import JSONResponse

from app.core.generator import classify_exception


# ---------------------------------------------------------------------------
# Structured error responses. Every failure path returns the same JSON shape so
# the frontend can render a typed error card (retry / fix-key / change-prompt)
# instead of dumping a raw exception string:
#   { error, error_code, detail_en, retryable, attempts? }
# ---------------------------------------------------------------------------
def _validation_error(message_pl: str, code: str, status: int = 400) -> JSONResponse:
    """A request-validation failure (bad/missing input) — never retryable."""
    return JSONResponse(
        {"error": message_pl, "error_code": code, "retryable": False},
        status_code=status,
    )


def _result_error(result, fallback: str = "Nieznany błąd generowania.") -> JSONResponse:
    """Structured response from a failed top-level GenerationResult."""
    return JSONResponse(
        {
            "error": result.error_message or fallback,
            "error_code": result.error_code or "UNKNOWN",
            "detail_en": result.error_detail,
            "retryable": bool(result.retryable),
            "attempts": result.attempts,
        },
        status_code=result.http_status or 500,
    )


def _item_error(base: dict, result_or_exc) -> dict:
    """Merge structured error fields into a per-item (variant / source) dict for
    the batch endpoints, classifying a raw gather exception when needed."""
    if isinstance(result_or_exc, Exception):
        info = classify_exception(result_or_exc)
        base.update(error=info.message_pl, error_code=info.error_code,
                    detail_en=str(result_or_exc), retryable=info.retryable)
    else:  # a GenerationResult
        r = result_or_exc
        base.update(error=r.error_message or "render failed",
                    error_code=r.error_code or "UNKNOWN",
                    detail_en=r.error_detail, retryable=bool(r.retryable))
    return base
