import json

from models import Schema
from pipeline.providers import LLMProvider

_SYSTEM = (
    "You are a data visualisation planner. Given a CSV schema and a user prompt, "
    "decide how many charts to generate and write a focused sub-prompt for each one.\n\n"
    "Rules:\n"
    "- If the user asks for a single chart or a simple question, return exactly 1 spec.\n"
    "- If the user asks for multiple charts, a dashboard, or references several metrics/dimensions, "
    "return one spec per chart (max 4).\n"
    "- Each sub_prompt must be self-contained — it will be sent to the chart pipeline without any "
    "other context, so include the relevant column names and chart intent explicitly.\n"
    "- Do NOT invent columns that are not in the schema.\n\n"
    "Respond with a JSON array only, no other text:\n"
    '[{"sub_prompt": "..."}]'
)


class Decomposer:
    def __init__(self, provider: LLMProvider):
        self._provider = provider

    def decompose(self, prompt: str, schema: Schema) -> list[str]:
        """
        Return a list of focused sub-prompts (1–4) derived from the user's prompt.
        Single-chart prompts return a list of one.
        """
        schema_desc = "\n".join(
            f"- {col.name} ({col.type.value})" for col in schema.columns
        )
        user_msg = f"Schema:\n{schema_desc}\n\nUser prompt: {prompt}"

        raw = self._provider.complete(_SYSTEM, user_msg).strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        start, end = raw.find("["), raw.rfind("]")
        if start == -1 or end == -1:
            raise ValueError(f"Decomposer did not return a JSON array: {raw[:200]}")

        specs = json.loads(raw[start : end + 1])
        if not isinstance(specs, list) or not specs:
            raise ValueError("Decomposer returned an empty or non-list response")

        sub_prompts = [s["sub_prompt"] for s in specs[:4] if s.get("sub_prompt")]
        if not sub_prompts:
            raise ValueError("Decomposer returned specs with no sub_prompt fields")

        return sub_prompts
