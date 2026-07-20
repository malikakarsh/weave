import hashlib
import logging
import os

from .base import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.0-flash"

# How long a cached system prompt lives server-side before it must be recreated.
# The new SDK takes ttl as a duration string.
_CACHE_TTL = "600s"


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

    def _cached_content(self, client, types, system: str, key) -> str | None:
        """Resource name of a server-side cache holding `system`, creating it if
        needed, or None if caching isn't available for this prompt/model. Gemini bills
        cached prompt tokens at a large discount. Every failure path (prompt below the
        cache minimum, cache expired/deleted) falls back to the uncached call, so
        generation never breaks — caching is a pure optimisation."""
        name = self._cache_names.get(key)
        if name:
            try:
                client.caches.get(name=name)          # still alive?
                return name
            except Exception:
                self._cache_names.pop(key, None)       # expired/deleted — recreate below

        try:
            cache = client.caches.create(
                model=self._model,
                config=types.CreateCachedContentConfig(
                    system_instruction=system, ttl=_CACHE_TTL,
                ),
            )
            self._cache_names[key] = cache.name
            return cache.name
        except Exception as e:
            # Most commonly the system prompt is below the model's minimum cacheable
            # size — nothing to do but use the uncached path.
            logger.debug("gemini prompt cache unavailable (%s); using uncached", e)
            return None

    def complete(self, system: str, user: str) -> str:
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError(
                "google-genai is required for GeminiProvider: pip install google-genai"
            )

        self.last_usage = None
        client = genai.Client(api_key=self._api_key)
        key = (self._model, hashlib.sha256(system.encode("utf-8")).hexdigest())

        cache_name = self._cached_content(client, types, system, key)
        try:
            response = self._generate(client, types, user, system, cache_name)
        except Exception:
            if not cache_name:
                raise
            # The cache may have expired between lookup and use — drop it, go uncached.
            self._cache_names.pop(key, None)
            response = self._generate(client, types, user, system, None)

        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            # prompt_token_count already includes any cached tokens, so 'tokens in'
            # stays comparable whether or not the cache was hit.
            self.last_usage = (
                int(getattr(meta, "prompt_token_count", 0) or 0),
                int(getattr(meta, "candidates_token_count", 0) or 0),
            )
        return (response.text or "").strip()

    def _generate(self, client, types, user: str, system: str, cache_name: str | None):
        """One generate_content call, using the server-side cache when available
        (system prompt lives in the cache) else inlining the system instruction."""
        config = (types.GenerateContentConfig(cached_content=cache_name) if cache_name
                  else types.GenerateContentConfig(system_instruction=system))
        return client.models.generate_content(
            model=self._model, contents=user, config=config,
        )
