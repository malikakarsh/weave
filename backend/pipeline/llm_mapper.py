import json

from models import AxisMapping, Schema
from pipeline.prompts import AXIS_MAPPING_SYSTEM, REFINE_SYSTEM
from pipeline.providers import LLMProvider, AnthropicProvider


class LLMMapper:
    def __init__(self, provider: LLMProvider | None = None):
        self._provider = provider or AnthropicProvider()
        self._system_prompt = AXIS_MAPPING_SYSTEM

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    def map(self, schema: Schema, prompt: str) -> AxisMapping:
        system, user = self.build_map_request(schema, prompt)
        raw = self._provider.complete(system, user)
        return self.parse_map_response(raw, schema)

    def build_map_request(self, schema: Schema, prompt: str) -> tuple[str, str]:
        """Return the (system, user) messages for an initial mapping request."""
        user_msg = (
            f"Dataset schema:\n{self._describe_schema(schema)}\n\n"
            f"User intent: {prompt}"
        )
        return self._system_prompt, user_msg

    def parse_map_response(self, raw: str, schema: Schema) -> AxisMapping:
        """Parse a raw LLM response into a validated AxisMapping for an initial mapping."""
        raw = self._strip_fences(raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {raw!r}") from e

        # LLMs sometimes return "null" as a string instead of JSON null
        for key in ("group_column", "group_filter", "top_n", "time_unit", "x_min", "x_max",
                    "z_column", "label_column", "facet_direction", "color", "category_colors"):
            if data.get(key) == "null":
                data[key] = None

        # y_column must always be a string; fall back to first numeric column if omitted
        if not data.get("y_column"):
            numeric_cols = [c.name for c in schema.columns if c.type.value == "Float"]
            data["y_column"] = numeric_cols[0] if numeric_cols else schema.columns[-1].name

        mapping = AxisMapping(**data)
        self._validate(mapping, [col.name for col in schema.columns])
        return mapping

    def refine(self, current_mapping: AxisMapping, history: list[dict], instruction: str) -> AxisMapping:
        """Return an updated AxisMapping by applying a natural-language instruction to the current one."""
        system, user = self.build_refine_request(current_mapping, history, instruction)
        raw = self._provider.complete(system, user)
        return self.parse_refine_response(raw, current_mapping)

    def build_refine_request(
        self, current_mapping: AxisMapping, history: list[dict], instruction: str
    ) -> tuple[str, str]:
        """Return the (system, user) messages for a refinement request."""
        history_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in history
        )
        user_msg = (
            f"Current mapping:\n{current_mapping.model_dump_json(indent=2)}\n\n"
            f"Conversation history:\n{history_text}\n\n"
            f"New instruction: {instruction}"
        )
        return REFINE_SYSTEM, user_msg

    def parse_refine_response(self, raw: str, current_mapping: AxisMapping) -> AxisMapping:
        """Parse a raw LLM response into a validated AxisMapping for a refinement."""
        raw = self._strip_fences(raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {raw!r}") from e

        for key in ("group_column", "group_filter", "top_n", "time_unit", "x_min", "x_max",
                    "z_column", "label_column", "facet_direction", "color", "category_colors"):
            if data.get(key) == "null":
                data[key] = None

        # Required string fields must never be None — fall back to current mapping
        current = current_mapping.model_dump()
        for key in ("aggregation", "sort_order", "chart_type", "x_column", "y_column"):
            if not data.get(key):
                data[key] = current[key]

        return AxisMapping(**data)

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
