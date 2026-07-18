import datetime
import hashlib
import logging
import os

from .base import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.0-flash"

# How long a cached system prompt lives server-side before it must be recreated.
_CACHE_TTL = datetime.timedelta(minutes=10)


class GeminiProvider(LLMProvider):
    # (model, sha256(system)) -> cached-content resource name, shared across every
    # provider instance in this process (a fresh provider is built per request, so
    # instance state wouldn't persist). Lets the large, identical system prompt be
    # uploaded once and reused across calls within its TTL.
    _cache_names: dict[tuple[str, str], str] = {}

    def __init__(self, model: str | None = None):
        self._model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self._api_key = os.getenv("GEMINI_API_KEY")
        if not self._api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set")

    @property
    def model(self) -> str:
        return self._model

    def _cached_model(self, genai, system: str):
        """A GenerativeModel backed by a server-side cache of `system`, or None if
        caching isn't available for this prompt/model. Gemini bills cached prompt
        tokens at a large discount. Every failure path (SDK too old, prompt below
        the cache minimum, cache expired/deleted) falls back to the uncached model,
        so generation never breaks — caching is a pure optimisation."""
        try:
            from google.generativeai import caching
        except Exception:
            return None

        key = (self._model, hashlib.sha256(system.encode("utf-8")).hexdigest())
        name = self._cache_names.get(key)
        if name:
            try:
                return genai.GenerativeModel.from_cached_content(
                    cached_content=caching.CachedContent.get(name)
                )
            except Exception:
                self._cache_names.pop(key, None)  # expired or deleted — recreate below

        try:
            cache = caching.CachedContent.create(
                model=self._model, system_instruction=system, ttl=_CACHE_TTL,
            )
            self._cache_names[key] = cache.name
            return genai.GenerativeModel.from_cached_content(cached_content=cache)
        except Exception as e:
            # Most commonly the system prompt is below the model's minimum cacheable
            # size — nothing to do but use the uncached path.
            logger.debug("gemini prompt cache unavailable (%s); using uncached", e)
            return None

    def complete(self, system: str, user: str) -> str:
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "google-generativeai is required for GeminiProvider: "
                "pip install google-generativeai"
            )

        self.last_usage = None
        genai.configure(api_key=self._api_key)
        model = self._cached_model(genai, system) or genai.GenerativeModel(
            self._model, system_instruction=system
        )
        response = model.generate_content(user)
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            # prompt_token_count already includes any cached tokens, so 'tokens in'
            # stays comparable whether or not the cache was hit.
            self.last_usage = (
                int(getattr(meta, "prompt_token_count", 0) or 0),
                int(getattr(meta, "candidates_token_count", 0) or 0),
            )
        return response.text.strip()
