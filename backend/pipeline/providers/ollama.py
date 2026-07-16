import os

from .base import LLMProvider

DEFAULT_MODEL = "gemma4:latest"


class OllamaProvider(LLMProvider):
    def __init__(self, model: str | None = None, num_ctx: int = 4096):
        self._base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self._model = model or os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
        self._num_ctx = num_ctx  # cap KV cache; models like gemma4 default to 1M ctx

    @property
    def model(self) -> str:
        return self._model

    def complete(self, system: str, user: str) -> str:
        try:
            import requests
        except ImportError:
            raise ImportError("requests is required for OllamaProvider: pip install requests")

        resp = requests.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"num_ctx": self._num_ctx},
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()
