from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor


class LLMProvider(ABC):
    # Token usage (input, output) of the most recent complete() call, or None
    # when the provider/model doesn't report it. Set inside complete(); read by
    # the metrics wrapper right after the call. Keeps complete() -> str intact.
    last_usage: tuple[int, int] | None = None

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Send a system + user message and return the text response."""
        ...

    def complete_batch(self, requests: list[tuple[str, str]]) -> list[str]:
        """Complete many (system, user) prompts at once, returning responses in order.

        Default implementation fans the calls out concurrently. Providers with a
        native batch endpoint (e.g. Anthropic Message Batches) override this.
        """
        if not requests:
            return []
        with ThreadPoolExecutor(max_workers=min(8, len(requests))) as pool:
            return list(pool.map(lambda r: self.complete(*r), requests))
