import json

from models import AxisMapping, Schema
from pipeline.prompts import AXIS_MAPPING_SYSTEM
from pipeline.providers import LLMProvider, AnthropicProvider


class LLMMapper:
    def __init__(self, provider: LLMProvider | None = None):
        self._provider = provider or AnthropicProvider()
        self._system_prompt = AXIS_MAPPING_SYSTEM

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    def map(self, schema: Schema, prompt: str) -> AxisMapping:
        user_msg = (
            f"Dataset schema:\n{self._describe_schema(schema)}\n\n"
            f"User intent: {prompt}"
        )
        raw = self._provider.complete(self._system_prompt, user_msg)
        raw = self._strip_fences(raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {raw!r}") from e

        # LLMs sometimes return "null" as a string instead of JSON null
        for key in ("group_column", "group_filter", "top_n", "time_unit", "x_min", "x_max",
                    "z_column", "label_column", "facet_direction"):
            if data.get(key) == "null":
                data[key] = None

        # y_column must always be a string; fall back to first numeric column if omitted
        if not data.get("y_column"):
            numeric_cols = [c.name for c in schema.columns if c.type.value == "Float"]
            data["y_column"] = numeric_cols[0] if numeric_cols else schema.columns[-1].name

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
        if mapping.group_column is not None and mapping.group_column not in column_names:
            raise ValueError(
                f"group_column '{mapping.group_column}' not in schema. Available: {column_names}"
            )
