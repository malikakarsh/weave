"""GeminiProvider on the google-genai SDK. We fake only the network client (the
Client class), keeping the REAL google.genai.types so the config objects the
provider builds are validated by the actual SDK schema."""

from types import SimpleNamespace

import pytest

from google import genai

from pipeline.providers.gemini import GeminiProvider


def _resp(text, pin=7, cout=3):
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(prompt_token_count=pin, candidates_token_count=cout),
    )


class _Caches:
    def __init__(self, create_raises=False):
        self.create_raises = create_raises
        self.created = 0

    def get(self, *, name):
        raise Exception("cache miss")            # force (re)create each time

    def create(self, *, model, config):
        if self.create_raises:
            raise Exception("prompt too small to cache")
        self.created += 1
        assert config.system_instruction          # real CreateCachedContentConfig
        return SimpleNamespace(name="cachedContents/abc")


class _Models:
    def __init__(self, sink):
        self.sink = sink

    def generate_content(self, *, model, contents, config):
        self.sink.append(SimpleNamespace(model=model, contents=contents, config=config))
        return _resp("  hello  ")


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    GeminiProvider._cache_names.clear()
    calls = []

    def make_client(create_raises):
        def _factory(*a, **k):
            return SimpleNamespace(caches=_Caches(create_raises), models=_Models(calls))
        return _factory

    return SimpleNamespace(monkeypatch=monkeypatch, calls=calls, make_client=make_client)


class TestGeminiProvider:
    def test_cached_path_sends_cached_content_and_reports_usage(self, patched):
        patched.monkeypatch.setattr(genai, "Client", patched.make_client(create_raises=False))
        p = GeminiProvider(model="gemini-2.0-flash")
        out = p.complete("SYSTEM PROMPT", "user question")
        assert out == "hello"                       # stripped
        assert p.last_usage == (7, 3)
        cfg = patched.calls[-1].config
        assert cfg.cached_content == "cachedContents/abc"  # system rode the cache
        assert cfg.system_instruction is None

    def test_falls_back_to_inline_system_when_cache_unavailable(self, patched):
        patched.monkeypatch.setattr(genai, "Client", patched.make_client(create_raises=True))
        p = GeminiProvider(model="gemini-2.0-flash")
        out = p.complete("SYSTEM PROMPT", "user question")
        assert out == "hello"
        cfg = patched.calls[-1].config
        assert cfg.cached_content is None
        assert cfg.system_instruction == "SYSTEM PROMPT"   # inlined instead

    def test_requires_api_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            GeminiProvider()
