"""LLM-call metrics: persist the buffered records and aggregate them for the
admin live panel (latency, volume, errors, tokens, estimated cost).

Capture happens in `pipeline/providers/metrics.py` (a thread-safe buffer). Here
we drain it into the `llm_calls` table and compute per-model aggregates. Cost is
derived from tokens + `MODEL_PRICING` at query time, so prices can change without
rewriting stored rows.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select

from api.db import SessionLocal
from api.db_models import LlmCall
from pipeline.providers.metrics import drain

# USD per 1,000,000 tokens: (input, output). Prefix-matched against the model
# name, longest prefix wins; unknown models → cost shown as null. Edit as needed.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4": (0.80, 4.0),
    "claude-3-5-haiku": (0.80, 4.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.0),
}


def _price(model: str) -> tuple[float, float] | None:
    best: tuple[float, float] | None = None
    best_len = -1
    for prefix, price in MODEL_PRICING.items():
        if model.startswith(prefix) and len(prefix) > best_len:
            best, best_len = price, len(prefix)
    return best


def cost(model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    """Estimated USD cost for a model given token counts, or None if unpriced."""
    price = _price(model)
    if price is None:
        return None
    pin, pout = price
    return round((input_tokens or 0) / 1e6 * pin + (output_tokens or 0) / 1e6 * pout, 6)


async def flush() -> int:
    """Persist all buffered call records to `llm_calls`. Returns rows written."""
    records = drain()
    if not records:
        return 0
    async with SessionLocal() as db:
        db.add_all([
            LlmCall(
                provider=r.provider, model=r.model, latency_ms=r.latency_ms, ok=r.ok,
                input_tokens=r.input_tokens, output_tokens=r.output_tokens,
            )
            for r in records
        ])
        await db.commit()
    return len(records)


async def aggregate() -> dict:
    """Per-(provider, model) performance plus overall totals, all-time, with a
    live calls/min from the last 60 seconds."""
    live_since = datetime.now(timezone.utc) - timedelta(seconds=60)

    errors = func.count().filter(LlmCall.ok.is_(False))
    live = func.count().filter(LlmCall.created_at >= live_since)
    p95 = func.percentile_cont(0.95).within_group(LlmCall.latency_ms.asc())

    stmt = (
        select(
            LlmCall.provider,
            LlmCall.model,
            func.count().label("calls"),
            errors.label("errors"),
            func.avg(LlmCall.latency_ms).label("avg_latency"),
            p95.label("p95_latency"),
            func.coalesce(func.sum(LlmCall.input_tokens), 0).label("in_tok"),
            func.coalesce(func.sum(LlmCall.output_tokens), 0).label("out_tok"),
            func.avg(LlmCall.input_tokens).label("avg_in_tok"),
            func.avg(LlmCall.output_tokens).label("avg_out_tok"),
            func.max(LlmCall.created_at).label("last_used"),
            live.label("live"),
        )
        .group_by(LlmCall.provider, LlmCall.model)
        .order_by(func.count().desc())
    )

    async with SessionLocal() as db:
        rows = (await db.execute(stmt)).all()

    models = []
    tot = {"calls": 0, "errors": 0, "in_tok": 0, "out_tok": 0, "cost": 0.0, "live": 0}
    for r in rows:
        c = cost(r.model, int(r.in_tok), int(r.out_tok))
        models.append({
            "provider": r.provider,
            "model": r.model,
            "calls": int(r.calls),
            "errors": int(r.errors),
            "error_rate": round(r.errors / r.calls, 4) if r.calls else 0.0,
            "avg_latency_ms": round(float(r.avg_latency)) if r.avg_latency is not None else None,
            "p95_latency_ms": round(float(r.p95_latency)) if r.p95_latency is not None else None,
            "input_tokens": int(r.in_tok),
            "output_tokens": int(r.out_tok),
            "avg_input_tokens": round(float(r.avg_in_tok)) if r.avg_in_tok is not None else None,
            "avg_output_tokens": round(float(r.avg_out_tok)) if r.avg_out_tok is not None else None,
            "cost_usd": c,
            "last_used": r.last_used.isoformat() if r.last_used else None,
            "calls_per_min": int(r.live),
        })
        tot["calls"] += int(r.calls)
        tot["errors"] += int(r.errors)
        tot["in_tok"] += int(r.in_tok)
        tot["out_tok"] += int(r.out_tok)
        tot["cost"] += c or 0.0
        tot["live"] += int(r.live)

    return {
        "models": models,
        "totals": {
            "calls": tot["calls"],
            "errors": tot["errors"],
            "error_rate": round(tot["errors"] / tot["calls"], 4) if tot["calls"] else 0.0,
            "input_tokens": tot["in_tok"],
            "output_tokens": tot["out_tok"],
            "avg_input_tokens": round(tot["in_tok"] / tot["calls"]) if tot["calls"] else None,
            "avg_output_tokens": round(tot["out_tok"] / tot["calls"]) if tot["calls"] else None,
            "cost_usd": round(tot["cost"], 6),
            "calls_per_min": tot["live"],
        },
        "ts": datetime.now(timezone.utc).isoformat(),
    }
