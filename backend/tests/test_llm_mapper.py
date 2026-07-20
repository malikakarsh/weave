import json

import pytest

from models import AxisMapping, ColumnInfo, ColumnType, Schema
from pipeline.llm_mapper import LLMMapper
from pipeline.providers.base import LLMProvider


class StubProvider(LLMProvider):
    """Configurable stub — call set_response() before each test."""
    def __init__(self, response: str = "{}"):
        self.response = response
        self.model = "stub"

    def complete(self, system: str, user: str) -> str:
        return self.response


@pytest.fixture
def stub():
    return StubProvider()


@pytest.fixture
def mapper(stub):
    return LLMMapper(provider=stub)


def _schema(*cols) -> Schema:
    """Build a Schema from (name, ColumnType) pairs."""
    column_infos = [ColumnInfo(name=n, type=t, sample=[]) for n, t in cols]
    return Schema(columns=column_infos, row_count=10)


# ── _strip_fences ─────────────────────────────────────────────────────────────

class TestStripFences:
    def test_plain_json_unchanged(self, mapper):
        raw = '{"chart_type": "bar"}'
        assert mapper._strip_fences(raw) == raw

    def test_json_fence_stripped(self, mapper):
        raw = '```json\n{"chart_type": "bar"}\n```'
        assert mapper._strip_fences(raw) == '{"chart_type": "bar"}'

    def test_plain_fence_stripped(self, mapper):
        raw = '```\n{"x": 1}\n```'
        assert mapper._strip_fences(raw) == '{"x": 1}'

    def test_strips_surrounding_whitespace(self, mapper):
        raw = '```json\n  {"x": 1}  \n```'
        assert mapper._strip_fences(raw) == '{"x": 1}'

    def test_no_fence_whitespace_stripped(self, mapper):
        raw = '  {"x": 1}  '
        assert mapper._strip_fences(raw) == '{"x": 1}'


# ── _describe_schema ──────────────────────────────────────────────────────────

class TestDescribeSchema:
    def test_includes_row_count(self, mapper):
        schema = _schema(("sales", ColumnType.FLOAT))
        schema = Schema(columns=schema.columns, row_count=42)
        desc = mapper._describe_schema(schema)
        assert "42" in desc

    def test_includes_column_name(self, mapper):
        schema = _schema(("revenue", ColumnType.FLOAT))
        desc = mapper._describe_schema(schema)
        assert "revenue" in desc

    def test_includes_column_type(self, mapper):
        schema = _schema(("date", ColumnType.DATE), ("value", ColumnType.FLOAT))
        desc = mapper._describe_schema(schema)
        assert "Date" in desc
        assert "Float" in desc

    def test_includes_samples(self, mapper):
        col = ColumnInfo(name="price", type=ColumnType.FLOAT, sample=["10", "20", "30"])
        schema = Schema(columns=[col], row_count=3)
        desc = mapper._describe_schema(schema)
        assert "10" in desc and "20" in desc

    def test_each_column_on_own_line(self, mapper):
        schema = _schema(("a", ColumnType.STRING), ("b", ColumnType.FLOAT))
        lines = mapper._describe_schema(schema).splitlines()
        assert any("a" in l for l in lines)
        assert any("b" in l for l in lines)


# ── _validate ─────────────────────────────────────────────────────────────────

class TestValidate:
    COLS = ["date", "revenue", "company"]

    def test_valid_mapping_no_error(self, mapper):
        m = AxisMapping(x_column="date", y_column="revenue")
        mapper._validate(m, self.COLS)  # must not raise

    def test_invalid_x_column_raises(self, mapper):
        m = AxisMapping(x_column="nonexistent", y_column="revenue")
        with pytest.raises(ValueError, match="x_column"):
            mapper._validate(m, self.COLS)

    def test_invalid_y_column_raises(self, mapper):
        m = AxisMapping(x_column="date", y_column="nonexistent")
        with pytest.raises(ValueError, match="y_column"):
            mapper._validate(m, self.COLS)

    def test_invalid_group_column_raises(self, mapper):
        m = AxisMapping(x_column="date", y_column="revenue", group_column="missing")
        with pytest.raises(ValueError, match="group_column"):
            mapper._validate(m, self.COLS)

    def test_null_group_column_passes(self, mapper):
        m = AxisMapping(x_column="date", y_column="revenue", group_column=None)
        mapper._validate(m, self.COLS)  # must not raise


# ── map() — mocked provider ───────────────────────────────────────────────────

class TestMap:
    def _valid_response(self, **overrides) -> str:
        base = {
            "chart_type": "bar",
            "x_column": "name",
            "y_column": "value",
            "group_column": None,
            "group_filter": None,
            "aggregation": "sum",
            "top_n": None,
            "sort_order": "asc",
            "time_unit": None,
            "x_min": None,
            "x_max": None,
            "z_column": None,
            "label_column": None,
            "facet_direction": None,
            "facet_free_y": False,
            "title": "Test",
            "x_label": "Name",
            "y_label": "Value",
            "color": None,
            "category_colors": None,
        }
        base.update(overrides)
        return json.dumps(base)

    def test_basic_map(self, stub, mapper):
        schema = _schema(("name", ColumnType.STRING), ("value", ColumnType.FLOAT))
        stub.response = self._valid_response()
        result = mapper.map(schema, "bar chart of names")
        assert result.chart_type == "bar"
        assert result.x_column == "name"
        assert result.y_column == "value"

    def test_null_string_cleaned_for_group_column(self, stub, mapper):
        schema = _schema(("name", ColumnType.STRING), ("value", ColumnType.FLOAT))
        stub.response = self._valid_response(group_column="null")
        result = mapper.map(schema, "bar chart")
        assert result.group_column is None

    def test_null_string_cleaned_for_time_unit(self, stub, mapper):
        schema = _schema(("date", ColumnType.DATE), ("value", ColumnType.FLOAT))
        stub.response = self._valid_response(x_column="date", time_unit="null")
        result = mapper.map(schema, "line chart")
        assert result.time_unit is None

    def test_null_string_cleaned_for_color(self, stub, mapper):
        schema = _schema(("name", ColumnType.STRING), ("value", ColumnType.FLOAT))
        stub.response = self._valid_response(color="null")
        result = mapper.map(schema, "bar chart")
        assert result.color is None

    def test_y_column_fallback_to_first_numeric(self, stub, mapper):
        schema = _schema(("name", ColumnType.STRING), ("revenue", ColumnType.FLOAT))
        # LLM omits y_column
        stub.response = self._valid_response(y_column="")
        result = mapper.map(schema, "bar chart")
        assert result.y_column == "revenue"

    def test_invalid_json_raises(self, stub, mapper):
        schema = _schema(("name", ColumnType.STRING), ("value", ColumnType.FLOAT))
        stub.response = "not valid json"
        with pytest.raises(ValueError, match="invalid JSON"):
            mapper.map(schema, "chart")

    def test_validate_called_raises_on_bad_column(self, stub, mapper):
        schema = _schema(("name", ColumnType.STRING), ("value", ColumnType.FLOAT))
        stub.response = self._valid_response(x_column="ghost_column")
        with pytest.raises(ValueError, match="x_column"):
            mapper.map(schema, "bar chart")


# ── refine() — mocked provider ────────────────────────────────────────────────

class TestRefine:
    BASE = AxisMapping(
        chart_type="bar",
        x_column="name",
        y_column="revenue",
        aggregation="sum",
        sort_order="asc",
    )

    def _refined_response(self, **overrides) -> str:
        base = self.BASE.model_dump()
        base.update(overrides)
        return json.dumps(base)

    def test_basic_refine(self, stub, mapper):
        stub.response = self._refined_response(sort_order="desc")
        result = mapper.refine(self.BASE, [], "sort descending")
        assert result.sort_order == "desc"

    def test_null_string_cleaned_in_refine(self, stub, mapper):
        stub.response = self._refined_response(group_column="null")
        result = mapper.refine(self.BASE, [], "remove grouping")
        assert result.group_column is None

    def test_required_field_fallback_chart_type(self, stub, mapper):
        data = self.BASE.model_dump()
        data.pop("chart_type")  # LLM omits required field
        stub.response = json.dumps(data)
        result = mapper.refine(self.BASE, [], "change color to red")
        assert result.chart_type == "bar"

    def test_required_field_fallback_x_column(self, stub, mapper):
        data = self.BASE.model_dump()
        data["x_column"] = ""  # LLM returns empty string
        stub.response = json.dumps(data)
        result = mapper.refine(self.BASE, [], "change color to red")
        assert result.x_column == "name"

    def test_required_field_fallback_y_column(self, stub, mapper):
        data = self.BASE.model_dump()
        data["y_column"] = ""
        stub.response = json.dumps(data)
        result = mapper.refine(self.BASE, [], "sort descending")
        assert result.y_column == "revenue"

    def test_required_field_fallback_aggregation(self, stub, mapper):
        data = self.BASE.model_dump()
        data["aggregation"] = ""
        stub.response = json.dumps(data)
        result = mapper.refine(self.BASE, [], "sort descending")
        assert result.aggregation == "sum"

    def test_required_field_fallback_sort_order(self, stub, mapper):
        data = self.BASE.model_dump()
        data["sort_order"] = ""
        stub.response = json.dumps(data)
        result = mapper.refine(self.BASE, [], "add grouping")
        assert result.sort_order == "asc"

    def test_non_required_field_can_change(self, stub, mapper):
        stub.response = self._refined_response(color="#ef4444")
        result = mapper.refine(self.BASE, [], "make it red")
        assert result.color == "#ef4444"

    def test_invalid_json_raises(self, stub, mapper):
        stub.response = "broken"
        with pytest.raises(ValueError, match="invalid JSON"):
            mapper.refine(self.BASE, [], "sort descending")

    def test_off_topic_refine_is_rejected(self, stub, mapper):
        # An off-topic / misuse instruction returns {"error": ...} (no mapping),
        # which surfaces as a PromptRejected the API turns into the error banner.
        from pipeline.decomposer import PromptRejected
        stub.response = '{"error": "That is a math question, not a chart change."}'
        with pytest.raises(PromptRejected, match="math question"):
            mapper.refine(self.BASE, [], "tell me what is 2 + 2")

    def test_error_key_alongside_mapping_is_not_a_rejection(self, stub, mapper):
        # A real mapping always carries chart_type, so a stray "error" field can't
        # be mistaken for a rejection.
        stub.response = self._refined_response(sort_order="desc", error="ignored")
        result = mapper.refine(self.BASE, [], "sort descending")
        assert result.sort_order == "desc"
