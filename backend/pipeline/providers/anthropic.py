import os

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

    def complete(self, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=256,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text.strip()
