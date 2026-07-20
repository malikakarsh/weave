import json
import re

from models import AxisMapping, Schema
from pipeline.prompts import AXIS_MAPPING_SYSTEM, REFINE_SYSTEM
from pipeline.providers import LLMProvider, AnthropicProvider

# Token stems that mark a measure as a CUMULATIVE / running-total / standings value
# rather than an additive fact. Summing such a column across the rows it repeats on
# double-counts (a season standing appears on every race row), so its terminal value
# (max) is the true figure. Matched per name-token (so 'outstanding' ≠ 'standing').
_CUMULATIVE_STEMS = ("standing", "cumulative", "running", "career", "ytd", "todate")


def _is_cumulative_measure(col: str) -> bool:
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", col)          # split camelCase
    tokens = [t for t in re.split(r"[^a-zA-Z0-9]+", spaced) if t]
    return any(t.lower().startswith(stem) for t in tokens for stem in _CUMULATIVE_STEMS)


def _prefer_terminal_agg(data: dict) -> None:
    """Flip a plain 'sum' to 'max' when the measure is a cumulative/standings column,
    in place. Only touches 'sum' — an explicit mean/count/min/max is left as asked."""
    if data.get("aggregation") == "sum" and _is_cumulative_measure(data.get("y_column", "")):
        data["aggregation"] = "max"


def _ungroup_degenerate(data: dict) -> None:
    """Grouping by the x-axis column is degenerate — each category band gets one
    skinny sub-slot plus a legend that repeats the x labels. It's what the LLM
    emits for 'make each <x> a different color', so convert it to what was meant:
    a flat chart colored per category (via a palette unless colors were given)."""
    if data.get("group_column") and data.get("group_column") == data.get("x_column"):
        data["group_column"] = None
        if not any(data.get(k) for k in ("color", "category_colors", "palette")):
            data["palette"] = "vibrant"


def _normalize_network_connections(data: dict) -> None:
    """Reconcile a network's threshold controls with what its nodes can carry.

    A 'minimum connections' filter has no column — it filters node DEGREE. The LLM
    borrows an identity (x/y) column for it, which makes the control indistinguishable
    from a real value threshold and un-referenceable by name on a later 'remove the
    connections filter'; rewrite it to a stable virtual column, 'connections'.

    A numeric VALUE threshold (e.g. 'constructor result points filter') filters the
    node's aggregated size, so the node must be weighted by that column — if the graph
    is unweighted, adopt the filtered column as the z_column (node weight)."""
    if data.get("chart_type") != "network":
        return
    ident = {data.get("x_column"), data.get("y_column")}
    value_cols = []
    for c in (data.get("controls") or []):
        if not (isinstance(c, dict) and c.get("kind") in ("min", "max")):
            continue
        if c.get("column") in ident:
            c["column"] = "connections"            # degree filter
        elif c.get("column") != "connections":
            value_cols.append(c["column"])         # a real value threshold
    if value_cols and not data.get("z_column"):
        data["z_column"] = value_cols[0]           # weight nodes so they carry the value


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
                    "z_column", "label_column", "facet_direction", "color", "category_colors", "group_labels", "controls",
                    "filters", "limit", "palette", "background", "mark_scale", "metric_columns"):
            if data.get(key) == "null":
                data[key] = None

        # x_column must always be a string; some chart types (e.g. radar with
        # metric_columns) don't need it — fall back to a real column so validation passes.
        if not data.get("x_column"):
            mc = data.get("metric_columns")
            data["x_column"] = (data.get("group_column")
                                or (mc[0] if isinstance(mc, list) and mc else None)
                                or schema.columns[0].name)

        # y_column must always be a string; fall back to first numeric column if omitted
        if not data.get("y_column"):
            numeric_cols = [c.name for c in schema.columns if c.type.value == "Float"]
            data["y_column"] = numeric_cols[0] if numeric_cols else schema.columns[-1].name

        # Required string fields must never be None/empty — fall back to defaults
        # (e.g. the LLM may return aggregation=null for chart types that don't aggregate).
        for key, default in (("aggregation", "sum"), ("sort_order", "asc"), ("chart_type", "line")):
            if not data.get(key):
                data[key] = default

        _prefer_terminal_agg(data)   # cumulative/standings column → max, not sum
        _ungroup_degenerate(data)    # group == x-axis → flat chart, per-category palette
        _normalize_network_connections(data)   # network degree filter → 'connections'
        mapping = AxisMapping(**data)
        self._validate(mapping, [col.name for col in schema.columns])
        return mapping

    def refine(self, current_mapping: AxisMapping, history: list[dict], instruction: str,
               schema: Schema | None = None) -> AxisMapping:
        """Return an updated AxisMapping by applying a natural-language instruction to the current one."""
        system, user = self.build_refine_request(current_mapping, history, instruction, schema)
        raw = self._provider.complete(system, user)
        return self.parse_refine_response(raw, current_mapping)

    def build_refine_request(
        self, current_mapping: AxisMapping, history: list[dict], instruction: str,
        schema: Schema | None = None,
    ) -> tuple[str, str]:
        """Return the (system, user) messages for a refinement request.

        When the schema is provided, include the available columns + types so the
        model can pick valid columns (especially when changing chart type)."""
        history_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in history
        )
        schema_text = f"Dataset schema:\n{self._describe_schema(schema)}\n\n" if schema else ""
        user_msg = (
            f"{schema_text}"
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
                    "z_column", "label_column", "facet_direction", "color", "category_colors", "group_labels", "controls",
                    "filters", "limit", "palette", "background", "mark_scale", "metric_columns"):
            if data.get(key) == "null":
                data[key] = None

        # Required string fields must never be None — fall back to current mapping
        current = current_mapping.model_dump()
        for key in ("aggregation", "sort_order", "chart_type", "x_column", "y_column"):
            if not data.get(key):
                data[key] = current[key]

        _prefer_terminal_agg(data)   # cumulative/standings column → max, not sum
        _ungroup_degenerate(data)    # group == x-axis → flat chart, per-category palette
        _normalize_network_connections(data)   # network degree filter → 'connections'
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
