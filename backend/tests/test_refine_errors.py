"""Refinements that can't be applied surface a clear error instead of silently
re-rendering the same chart: a referenced column that isn't in the data, and a
no-op instruction the model couldn't map to any change."""

import csv

import pytest

from models.spec import AxisMapping, ChartConfig, FilterSpec
from models.schema import Schema, ColumnInfo, ColumnType
from pipeline.pipeline import Pipeline, _missing_column, _promote_threshold_filter
from pipeline.data_loader import DataLoader
from pipeline.transformer import Transformer
from pipeline.templater import Templater


def _schema():
    return Schema(row_count=5, columns=[
        ColumnInfo(name="cut", type=ColumnType.STRING, sample=["A"]),
        ColumnInfo(name="price", type=ColumnType.FLOAT, sample=["1"]),
    ])


class TestMissingColumn:
    def test_missing_group_column_named(self):
        m = AxisMapping(chart_type="bar", x_column="cut", y_column="price", group_column="clarity")
        msg = _missing_column(m, _schema())
        assert msg is not None
        assert "clarity" in msg and "cut, price" in msg

    def test_missing_metric_column(self):
        m = AxisMapping(chart_type="radar", x_column="cut", y_column="price",
                        metric_columns=["price", "carat"])
        msg = _missing_column(m, _schema())
        assert msg is not None and "carat" in msg

    def test_all_columns_present(self):
        m = AxisMapping(chart_type="bar", x_column="cut", y_column="price")
        assert _missing_column(m, _schema()) is None


class TestPromoteThresholdFilter:
    def test_bare_max_filter_becomes_control(self):
        # "add a maximum sepal width filter" (no number) → the LLM's hard filter is
        # promoted to a max slider so it can't empty the chart.
        m = AxisMapping(chart_type="scatter", x_column="len", y_column="width",
                        filters=[FilterSpec(column="width", max="3.0")])
        out = _promote_threshold_filter(m, "add a maximum sepal width filter")
        assert out.filters is None
        assert [(c.column, c.kind) for c in out.controls] == [("width", "max")]

    def test_explicit_number_stays_a_hard_filter(self):
        m = AxisMapping(chart_type="bar", x_column="cut", y_column="price",
                        filters=[FilterSpec(column="price", min="100")])
        out = _promote_threshold_filter(m, "only where price is at least 100")
        assert out.filters is not None and out.controls is None

    def test_category_filter_untouched(self):
        m = AxisMapping(chart_type="bar", x_column="cut", y_column="price",
                        filters=[FilterSpec(column="cut", values=["Ideal"])])
        out = _promote_threshold_filter(m, "add a maximum price filter")
        assert out.filters == m.filters and out.controls is None

    def test_no_slider_intent_leaves_filters(self):
        m = AxisMapping(chart_type="bar", x_column="cut", y_column="price",
                        filters=[FilterSpec(column="price", min="5")])
        out = _promote_threshold_filter(m, "sort descending")
        assert out.filters == m.filters


class _FakeMapper:
    """A mapper whose refine returns whatever mapping the test seeds."""
    def __init__(self, out):
        self._out = out
    def refine(self, current, history, instruction, schema):
        return self._out


def _pipeline(mapper):
    p = Pipeline.__new__(Pipeline)
    p._loader = DataLoader(); p._transformer = Transformer()
    p._templater = Templater(); p._mapper = mapper
    return p


def _csv(tmp_path):
    p = tmp_path / "d.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["cut", "price"])
        for i in range(5):
            w.writerow(["A", i])
    return str(p)


class TestRefineErrors:
    def test_noop_refine_raises(self, tmp_path):
        cur = AxisMapping(chart_type="bar", x_column="cut", y_column="price", aggregation="sum")
        p = _pipeline(_FakeMapper(cur.model_copy()))   # unchanged mapping
        with pytest.raises(ValueError, match="unchanged"):
            p.refine(_csv(tmp_path), cur, [], "do something impossible", ChartConfig(chart_type="bar"))

    def test_missing_column_refine_raises(self, tmp_path):
        cur = AxisMapping(chart_type="bar", x_column="cut", y_column="price", aggregation="sum")
        bad = cur.model_copy(update={"group_column": "clarity"})
        p = _pipeline(_FakeMapper(bad))
        with pytest.raises(ValueError, match="clarity"):
            p.refine(_csv(tmp_path), cur, [], "color by clarity", ChartConfig(chart_type="bar"))

    def test_valid_refine_succeeds(self, tmp_path):
        cur = AxisMapping(chart_type="bar", x_column="cut", y_column="price", aggregation="sum")
        changed = cur.model_copy(update={"sort_order": "desc"})
        p = _pipeline(_FakeMapper(changed))
        html, m = p.refine(_csv(tmp_path), cur, [], "sort descending", ChartConfig(chart_type="bar"))
        assert m.sort_order == "desc" and 'id="chart"' in html
