import os

from .base import LLMProvider
from .anthropic import AnthropicProvider
from .ollama import OllamaProvider
from .gemini import GeminiProvider
from .metrics import MeteredProvider

__all__ = ["LLMProvider", "AnthropicProvider", "OllamaProvider", "GeminiProvider", "get_provider"]


def get_provider(name: str | None = None, model: str | None = None) -> LLMProvider:
    """Return an LLMProvider from the name (defaults to LLM_PROVIDER env var or
    'anthropic'), wrapped so every LLM call is timed and metered."""
    name = (name or os.getenv("LLM_PROVIDER", "anthropic")).lower()
    if name == "anthropic":
        inner: LLMProvider = AnthropicProvider(model=model)
    elif name == "ollama":
        inner = OllamaProvider(model=model)
    elif name == "gemini":
        inner = GeminiProvider(model=model)
    else:
        raise ValueError(f"Unknown provider {name!r}. Choose from: anthropic, ollama, gemini")
    return MeteredProvider(inner, name)
