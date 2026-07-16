import os

from .base import LLMProvider
from .anthropic import AnthropicProvider
from .ollama import OllamaProvider
from .gemini import GeminiProvider

__all__ = ["LLMProvider", "AnthropicProvider", "OllamaProvider", "GeminiProvider", "get_provider"]


def get_provider(name: str | None = None, model: str | None = None) -> LLMProvider:
    """Return an LLMProvider from the name (defaults to LLM_PROVIDER env var or 'anthropic')."""
    name = (name or os.getenv("LLM_PROVIDER", "anthropic")).lower()
    if name == "anthropic":
        return AnthropicProvider(model=model)
    if name == "ollama":
        return OllamaProvider(model=model)
    if name == "gemini":
        return GeminiProvider(model=model)
    raise ValueError(f"Unknown provider {name!r}. Choose from: anthropic, ollama, gemini")
