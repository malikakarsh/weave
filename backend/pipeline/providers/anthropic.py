import os
import time

from .base import LLMProvider

DEFAULT_MODEL = "claude-haiku-4-5"


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str | None = None):
        import anthropic
        self._client = anthropic.Anthropic()
        self._model = model or os.getenv("CLAUDE_MODEL", DEFAULT_MODEL)

    @property
    def model(self) -> str:
        return self._model

    @staticmethod
    def _cacheable_system(system: str) -> list[dict]:
        """The system prompt as a single cacheable content block. `cache_control`
        marks it for Anthropic's prompt cache (~5-min TTL): the large, identical
        instruction block is stored server-side after the first call and read back
        at a fraction of the input cost on subsequent calls. If the prompt is below
        the model's minimum cacheable size, Anthropic silently ignores the flag —
        no error, same behaviour as before."""
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    @staticmethod
    def _total_input(usage) -> int:
        """Total input tokens processed, counting cache reads/writes so the metered
        'tokens in' stays comparable to the pre-caching numbers."""
        return (
            int(getattr(usage, "input_tokens", 0) or 0)
            + int(getattr(usage, "cache_read_input_tokens", 0) or 0)
            + int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        )

    def complete(self, system: str, user: str) -> str:
        self.last_usage = None
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=256,
            system=self._cacheable_system(system),
            messages=[{"role": "user", "content": user}],
        )
        usage = getattr(msg, "usage", None)
        if usage is not None:
            self.last_usage = (self._total_input(usage), int(usage.output_tokens))
        return msg.content[0].text.strip()

    def complete_batch(self, requests: list[tuple[str, str]]) -> list[str]:
        """Submit all prompts via the Anthropic Message Batches API and collect
        the results in request order. Errored items come back as empty strings."""
        if not requests:
            return []

        batch = self._client.messages.batches.create(
            requests=[
                {
                    "custom_id": f"req-{i}",
                    "params": {
                        "model": self._model,
                        "max_tokens": 256,
                        "system": self._cacheable_system(system),
                        "messages": [{"role": "user", "content": user}],
                    },
                }
                for i, (system, user) in enumerate(requests)
            ]
        )

        # Poll until the batch finishes processing.
        while True:
            status = self._client.messages.batches.retrieve(batch.id)
            if status.processing_status == "ended":
                break
            time.sleep(3)

        results: dict[str, str] = {}
        for entry in self._client.messages.batches.results(batch.id):
            if entry.result.type == "succeeded":
                results[entry.custom_id] = entry.result.message.content[0].text.strip()
            else:
                results[entry.custom_id] = ""

        return [results.get(f"req-{i}", "") for i in range(len(requests))]
