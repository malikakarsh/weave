import os

from .base import LLMProvider

DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider(LLMProvider):
    def __init__(self, model: str | None = None):
        self._model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self._api_key = os.getenv("GEMINI_API_KEY")
        if not self._api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set")

    @property
    def model(self) -> str:
        return self._model

    def complete(self, system: str, user: str) -> str:
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "google-generativeai is required for GeminiProvider: "
                "pip install google-generativeai"
            )

        genai.configure(api_key=self._api_key)
        model = genai.GenerativeModel(self._model, system_instruction=system)
        response = model.generate_content(user)
        return response.text.strip()
