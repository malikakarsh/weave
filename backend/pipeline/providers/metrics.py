"""In-process capture of LLM-call metrics.

`MeteredProvider` wraps any `LLMProvider` and, for every `complete()` call,
records the provider, model, latency, success, and token usage into a
thread-safe ring buffer. The API layer periodically `drain()`s the buffer and
persists it to Postgres (see `api/metrics.py`) — this keeps the pipeline layer
free of any DB/`api` dependency, and keeps the hot path non-blocking.
"""

import threading
import time
from collections import deque
from dataclasses import dataclass

from .base import LLMProvider

# Bounded so a long run without a flusher can't grow without limit; the API
# flusher drains every couple of seconds so this normally stays near-empty.
_BUFFER: deque["CallRecord"] = deque(maxlen=20000)
_LOCK = threading.Lock()


@dataclass
class CallRecord:
    provider: str
    model: str
    latency_ms: int
    ok: bool
    input_tokens: int | None
    output_tokens: int | None


def record(rec: CallRecord) -> None:
    with _LOCK:
        _BUFFER.append(rec)


def drain() -> list[CallRecord]:
    """Atomically remove and return all buffered records."""
    with _LOCK:
        out = list(_BUFFER)
        _BUFFER.clear()
    return out


class MeteredProvider(LLMProvider):
    """Times each `complete()` and buffers a `CallRecord`. Transparent otherwise
    — delegates behaviour to the wrapped provider and re-raises its errors."""

    def __init__(self, inner: LLMProvider, provider_name: str):
        self._inner = inner
        self._name = provider_name

    @property
    def model(self) -> str:
        return getattr(self._inner, "model", "unknown")

    def complete(self, system: str, user: str) -> str:
        self._inner.last_usage = None
        t0 = time.perf_counter()
        ok = True
        try:
            return self._inner.complete(system, user)
        except Exception:
            ok = False
            raise
        finally:
            usage = self._inner.last_usage
            record(CallRecord(
                provider=self._name,
                model=getattr(self._inner, "model", "unknown"),
                latency_ms=int((time.perf_counter() - t0) * 1000),
                ok=ok,
                input_tokens=usage[0] if usage else None,
                output_tokens=usage[1] if usage else None,
            ))

    # complete_batch is inherited from LLMProvider: it fans out to self.complete,
    # so each call in a batch is metered individually.
