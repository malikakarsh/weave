import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

from models import AxisMapping, Schema
from pipeline.prompts import AXIS_MAPPING_SYSTEM

DEFAULT_MODEL = "claude-haiku-4-5"


class LLMMapper:
    def __init__(self, system_prompt: str = AXIS_MAPPING_SYSTEM):
        self._client = anthropic.Anthropic()
        self._model = os.getenv("CLAUDE_MODEL", DEFAULT_MODEL)
        self._system_prompt = system_prompt

    def map(self, schema: Schema, prompt: str) -> AxisMapping:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=256,
            system=self._system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Dataset schema:\n{self._describe_schema(schema)}\n\n"
                        f"User intent: {prompt}\n\n"
                        "Pick the best x_column (Date) and y_column (Float)."
                    ),
                }
            ],
        )

        raw = response.content[0].text.strip()
        raw = self._strip_fences(raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {raw!r}") from e

        mapping = AxisMapping(**data)
        self._validate(mapping, [col.name for col in schema.columns])
        return mapping

    def _strip_fences(self, text: str) -> str:
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        return text.strip()

    def _describe_schema(self, schema: Schema) -> str:
        lines = [f"Total rows: {schema.row_count}"]
        for col in schema.columns:
            samples = ", ".join(str(s) for s in col.sample)
            lines.append(f"- {col.name} ({col.type.value}): samples = [{samples}]")
        return "\n".join(lines)

    def _validate(self, mapping: AxisMapping, column_names: list[str]) -> None:
        if mapping.x_column not in column_names:
            raise ValueError(
                f"x_column '{mapping.x_column}' not in schema. Available: {column_names}"
            )
        if mapping.y_column not in column_names:
            raise ValueError(
                f"y_column '{mapping.y_column}' not in schema. Available: {column_names}"
            )
