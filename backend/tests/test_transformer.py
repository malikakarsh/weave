import pytest

from models import AxisMapping
from pipeline.transformer import Transformer, _truncate, _in_range


@pytest.fixture
def t():
    return Transformer()


def mapping(**kwargs) -> AxisMapping:
    defaults = dict(x_column="x", y_column="y", aggregation="sum", sort_order="none")
    defaults.update(kwargs)
    return AxisMapping(**defaults)


# ── Module-level helpers ──────────────────────────────────────────────────────

class TestTruncate:
    def test_year(self):
        assert _truncate("2024-07-15", "year") == "2024-01-01"

    def test_month(self):
        assert _truncate("2024-07-15", "month") == "2024-07-01"

    def test_day(self):
        assert _truncate("2024-07-15", "day") == "2024-07-15"

    def test_datetime_year(self):
        assert _truncate("2024-07-15 12:30:00", "year") == "2024-01-01"

    def test_datetime_month(self):
        assert _truncate("2024-07-15 12:30:00", "month") == "2024-07-01"

    def test_unknown_unit_returns_original(self):
        assert _truncate("2024-07-15", "week") == "2024-07-15"

    def test_unparseable_returns_none(self):
        assert _truncate("not-a-date", "year") is None


class TestInRange:
    def test_no_bounds_always_true(self):
        assert _in_range("anything", None, None) is True

    def test_date_within_range(self):
        assert _in_range("2024-06-01", "2024-01-01", "2024-12-31") is True

    def test_date_below_min(self):
        assert _in_range("2023-12-31", "2024-01-01", None) is False

    def test_date_above_max(self):
        assert _in_range("2025-01-01", None, "2024-12-31") is False

    def test_date_equal_min_is_inclusive(self):
        assert _in_range("2024-01-01", "2024-01-01", None) is True

    def test_date_equal_max_is_inclusive(self):
        assert _in_range("2024-12-31", None, "2024-12-31") is True

    def test_float_within_range(self):
        assert _in_range("50", "10", "100") is True

    def test_float_below_min(self):
        assert _in_range("5", "10", None) is False

    def test_float_above_max(self):
        assert _in_range("200", None, "100") is False

    def test_only_x_min(self):
        assert _in_range("2024-06-01", "2024-01-01", None) is True

    def test_only_x_max(self):
        assert _in_range("2024-06-01", None, "2024-12-31") is True


# ── _sort ─────────────────────────────────────────────────────────────────────

class TestSort:
    DATA = [{"x": "A", "y": 30}, {"x": "B", "y": 10}, {"x": "C", "y": 20}]

    def test_asc(self):
        result = Transformer._sort(self.DATA, "asc")
        assert [d["y"] for d in result] == [10, 20, 30]

    def test_desc(self):
        result = Transformer._sort(self.DATA, "desc")
        assert [d["y"] for d in result] == [30, 20, 10]

    def test_none_preserves_order(self):
        result = Transformer._sort(self.DATA, "none")
        assert [d["x"] for d in result] == ["A", "B", "C"]

    def test_null_y_goes_last(self):
        data = [{"x": "A", "y": None}, {"x": "B", "y": 5}]
        result = Transformer._sort(data, "asc")
        assert result[0]["x"] == "B"
        assert result[-1]["x"] == "A"

    def test_null_y_goes_first_desc(self):
        # In desc mode the tuple (True, 0) for None sorts before (False, 5) when reversed
        data = [{"x": "A", "y": None}, {"x": "B", "y": 5}]
        result = Transformer._sort(data, "desc")
        assert result[0]["x"] == "A"
        assert result[-1]["x"] == "B"


# ── _transform_flat ───────────────────────────────────────────────────────────

class TestTransformFlat:
    ROWS = [
        {"x": "A", "y": "10"},
        {"x": "A", "y": "20"},
        {"x": "B", "y": "15"},
        {"x": "C", "y": "5"},
    ]

    def test_sum_aggregation(self, t):
        m = mapping(chart_type="bar", x_column="x", y_column="y", aggregation="sum")
        result = t._transform_flat(self.ROWS, m)
        by_x = {d["x"]: d["y"] for d in result}
        assert by_x["A"] == 30
        assert by_x["B"] == 15
        assert by_x["C"] == 5

    def test_mean_aggregation(self, t):
        m = mapping(chart_type="bar", x_column="x", y_column="y", aggregation="mean")
        result = t._transform_flat(self.ROWS, m)
        by_x = {d["x"]: d["y"] for d in result}
        assert by_x["A"] == 15.0
        assert by_x["B"] == 15.0

    def test_count_aggregation(self, t):
        m = mapping(chart_type="bar", x_column="x", y_column="y", aggregation="count")
        result = t._transform_flat(self.ROWS, m)
        by_x = {d["x"]: d["y"] for d in result}
        assert by_x["A"] == 2.0
        assert by_x["B"] == 1.0

    def test_min_aggregation(self, t):
        m = mapping(chart_type="bar", x_column="x", y_column="y", aggregation="min")
        result = t._transform_flat(self.ROWS, m)
        by_x = {d["x"]: d["y"] for d in result}
        assert by_x["A"] == 10.0

    def test_max_aggregation(self, t):
        m = mapping(chart_type="bar", x_column="x", y_column="y", aggregation="max")
        result = t._transform_flat(self.ROWS, m)
        by_x = {d["x"]: d["y"] for d in result}
        assert by_x["A"] == 20.0

    def test_sort_asc(self, t):
        m = mapping(chart_type="bar", x_column="x", y_column="y", aggregation="sum", sort_order="asc")
        result = t._transform_flat(self.ROWS, m)
        ys = [d["y"] for d in result]
        assert ys == sorted(ys)

    def test_sort_desc(self, t):
        m = mapping(chart_type="bar", x_column="x", y_column="y", aggregation="sum", sort_order="desc")
        result = t._transform_flat(self.ROWS, m)
        ys = [d["y"] for d in result]
        assert ys == sorted(ys, reverse=True)

    def test_top_n(self, t):
        m = mapping(chart_type="bar", x_column="x", y_column="y", aggregation="sum", top_n=2)
        result = t._transform_flat(self.ROWS, m)
        assert len(result) == 2
        # top 2 by sum: A=30, B=15 — C=5 excluded
        xs = {d["x"] for d in result}
        assert "C" not in xs

    def test_group_filter_as_x_filter(self, t):
        m = mapping(
            chart_type="bar", x_column="x", y_column="y",
            aggregation="sum", group_filter=["A", "B"],
        )
        result = t._transform_flat(self.ROWS, m)
        xs = {d["x"] for d in result}
        assert xs == {"A", "B"}
        assert "C" not in xs

    def test_x_min_filter(self, t):
        rows = [
            {"x": "2024-01-01", "y": "10"},
            {"x": "2024-06-01", "y": "20"},
            {"x": "2025-01-01", "y": "30"},
        ]
        m = mapping(x_column="x", y_column="y", x_min="2024-06-01")
        result = t._transform_flat(rows, m)
        xs = {d["x"] for d in result}
        assert "2024-01-01" not in xs
        assert "2024-06-01" in xs
        assert "2025-01-01" in xs

    def test_x_max_filter(self, t):
        rows = [
            {"x": "2024-01-01", "y": "10"},
            {"x": "2024-06-01", "y": "20"},
            {"x": "2025-01-01", "y": "30"},
        ]
        m = mapping(x_column="x", y_column="y", x_max="2024-06-01")
        result = t._transform_flat(rows, m)
        xs = {d["x"] for d in result}
        assert "2025-01-01" not in xs
        assert "2024-01-01" in xs
        assert "2024-06-01" in xs

    def test_time_unit_year_bucketing(self, t):
        rows = [
            {"x": "2024-01-15", "y": "10"},
            {"x": "2024-07-01", "y": "20"},
            {"x": "2023-05-01", "y": "5"},
        ]
        m = mapping(x_column="x", y_column="y", aggregation="sum", time_unit="year")
        result = t._transform_flat(rows, m)
        by_x = {d["x"]: d["y"] for d in result}
        assert by_x["2024-01-01"] == 30.0
        assert by_x["2023-01-01"] == 5.0

    def test_time_unit_month_bucketing(self, t):
        rows = [
            {"x": "2024-03-01", "y": "10"},
            {"x": "2024-03-15", "y": "5"},
            {"x": "2024-04-01", "y": "20"},
        ]
        m = mapping(x_column="x", y_column="y", aggregation="sum", time_unit="month")
        result = t._transform_flat(rows, m)
        by_x = {d["x"]: d["y"] for d in result}
        assert by_x["2024-03-01"] == 15.0
        assert by_x["2024-04-01"] == 20.0


# ── _transform_grouped ────────────────────────────────────────────────────────

class TestTransformGrouped:
    ROWS = [
        {"date": "2024-01-01", "revenue": "100", "company": "Acme"},
        {"date": "2024-01-01", "revenue": "200", "company": "Beta"},
        {"date": "2024-02-01", "revenue": "150", "company": "Acme"},
        {"date": "2024-02-01", "revenue": "250", "company": "Beta"},
        {"date": "2024-03-01", "revenue": "300", "company": "Gamma"},
    ]

    def _m(self, **kwargs):
        defaults = dict(
            chart_type="line",
            x_column="date",
            y_column="revenue",
            group_column="company",
            aggregation="sum",
            sort_order="none",
        )
        defaults.update(kwargs)
        return AxisMapping(**defaults)

    def test_grouped_shape(self, t):
        result = t._transform_grouped(self.ROWS, self._m())
        assert all("group" in g and "values" in g for g in result)

    def test_all_groups_present(self, t):
        result = t._transform_grouped(self.ROWS, self._m())
        groups = {g["group"] for g in result}
        assert groups == {"Acme", "Beta", "Gamma"}

    def test_values_count_per_group(self, t):
        result = t._transform_grouped(self.ROWS, self._m())
        by_group = {g["group"]: g["values"] for g in result}
        assert len(by_group["Acme"]) == 2
        assert len(by_group["Beta"]) == 2
        assert len(by_group["Gamma"]) == 1

    def test_group_filter(self, t):
        m = self._m(group_filter=["Acme", "Beta"])
        result = t._transform_grouped(self.ROWS, m)
        groups = {g["group"] for g in result}
        assert groups == {"Acme", "Beta"}
        assert "Gamma" not in groups

    def test_top_n_groups(self, t):
        m = self._m(top_n=2)
        result = t._transform_grouped(self.ROWS, m)
        assert len(result) == 2
        # Beta total = 450, Acme = 250, Gamma = 300
        groups = {g["group"] for g in result}
        assert "Acme" not in groups  # lowest total

    def test_sort_order_asc_by_x_totals(self, t):
        rows = [
            {"x": "B", "y": "30", "g": "G1"},
            {"x": "A", "y": "10", "g": "G1"},
            {"x": "C", "y": "20", "g": "G1"},
        ]
        m = AxisMapping(
            chart_type="bar", x_column="x", y_column="y",
            group_column="g", aggregation="sum", sort_order="asc",
        )
        result = t._transform_grouped(rows, m)
        xs = [pt["x"] for pt in result[0]["values"]]
        assert xs == ["A", "C", "B"]

    def test_sort_order_desc_by_x_totals(self, t):
        rows = [
            {"x": "B", "y": "30", "g": "G1"},
            {"x": "A", "y": "10", "g": "G1"},
            {"x": "C", "y": "20", "g": "G1"},
        ]
        m = AxisMapping(
            chart_type="bar", x_column="x", y_column="y",
            group_column="g", aggregation="sum", sort_order="desc",
        )
        result = t._transform_grouped(rows, m)
        xs = [pt["x"] for pt in result[0]["values"]]
        assert xs == ["B", "C", "A"]


# ── _transform_heatmap ────────────────────────────────────────────────────────

class TestTransformHeatmap:
    ROWS = [
        {"weekday": "Mon", "hour": "9",  "count": "5"},
        {"weekday": "Mon", "hour": "10", "count": "8"},
        {"weekday": "Tue", "hour": "9",  "count": "3"},
        {"weekday": "Mon", "hour": "9",  "count": "2"},  # duplicate → aggregated
    ]

    def test_cell_shape(self, t):
        m = AxisMapping(
            chart_type="heatmap", x_column="weekday", y_column="hour",
            z_column="count", aggregation="sum",
        )
        result = t._transform_heatmap(self.ROWS, m)
        assert all("x" in c and "y" in c and "z" in c for c in result)

    def test_aggregates_duplicate_cells(self, t):
        m = AxisMapping(
            chart_type="heatmap", x_column="weekday", y_column="hour",
            z_column="count", aggregation="sum",
        )
        result = t._transform_heatmap(self.ROWS, m)
        mon9 = next(c for c in result if c["x"] == "Mon" and c["y"] == "9")
        assert mon9["z"] == 7.0  # 5 + 2

    def test_count_without_z_column(self, t):
        m = AxisMapping(
            chart_type="heatmap", x_column="weekday", y_column="hour",
            aggregation="sum",
        )
        result = t._transform_heatmap(self.ROWS, m)
        mon9 = next(c for c in result if c["x"] == "Mon" and c["y"] == "9")
        assert mon9["z"] == 2.0  # count of rows

    def test_unique_cells_count(self, t):
        m = AxisMapping(
            chart_type="heatmap", x_column="weekday", y_column="hour",
            z_column="count", aggregation="sum",
        )
        result = t._transform_heatmap(self.ROWS, m)
        # 3 distinct (weekday, hour) pairs: Mon-9, Mon-10, Tue-9
        assert len(result) == 3


# ── _transform_network ────────────────────────────────────────────────────────

class TestTransformNetwork:
    ROWS = [
        {"src": "A", "tgt": "B", "w": "10"},
        {"src": "A", "tgt": "C", "w": "5"},
        {"src": "B", "tgt": "C", "w": "3"},
        {"src": "A", "tgt": "B", "w": "2"},  # duplicate edge → aggregated
    ]

    def test_result_shape(self, t):
        m = AxisMapping(chart_type="network", x_column="src", y_column="tgt", z_column="w", aggregation="sum")
        result = t._transform_network(self.ROWS, m)
        assert "nodes" in result and "links" in result

    def test_node_count(self, t):
        m = AxisMapping(chart_type="network", x_column="src", y_column="tgt", z_column="w", aggregation="sum")
        result = t._transform_network(self.ROWS, m)
        assert len(result["nodes"]) == 3  # A, B, C

    def test_link_count_deduped(self, t):
        m = AxisMapping(chart_type="network", x_column="src", y_column="tgt", z_column="w", aggregation="sum")
        result = t._transform_network(self.ROWS, m)
        assert len(result["links"]) == 3  # A-B, A-C, B-C

    def test_edge_weight_sum(self, t):
        m = AxisMapping(chart_type="network", x_column="src", y_column="tgt", z_column="w", aggregation="sum")
        result = t._transform_network(self.ROWS, m)
        ab = next(l for l in result["links"] if l["source"] == "A" and l["target"] == "B")
        assert ab["weight"] == 12.0  # 10 + 2

    def test_unweighted_links_count_as_one(self, t):
        m = AxisMapping(chart_type="network", x_column="src", y_column="tgt", aggregation="sum")
        result = t._transform_network(self.ROWS, m)
        ab = next(l for l in result["links"] if l["source"] == "A" and l["target"] == "B")
        assert ab["weight"] == 2.0  # 2 occurrences


# ── _transform_map ────────────────────────────────────────────────────────────

class TestTransformMap:
    ROWS = [
        {"lon": "-73.9857", "lat": "40.7484", "city": "New York", "pop": "8000000"},
        {"lon": "-87.6298", "lat": "41.8781", "city": "Chicago",  "pop": "2700000"},
    ]

    def test_each_row_becomes_one_point(self, t):
        m = AxisMapping(chart_type="symbol_map", x_column="lon", y_column="lat")
        result = t._transform_map(self.ROWS, m)
        assert len(result) == 2

    def test_coords_are_floats(self, t):
        m = AxisMapping(chart_type="symbol_map", x_column="lon", y_column="lat")
        result = t._transform_map(self.ROWS, m)
        assert isinstance(result[0]["x"], float)
        assert isinstance(result[0]["y"], float)

    def test_label_column_included(self, t):
        m = AxisMapping(chart_type="symbol_map", x_column="lon", y_column="lat", label_column="city")
        result = t._transform_map(self.ROWS, m)
        assert result[0]["label"] == "New York"

    def test_z_column_included(self, t):
        m = AxisMapping(chart_type="symbol_map", x_column="lon", y_column="lat", z_column="pop")
        result = t._transform_map(self.ROWS, m)
        assert result[0]["z"] == 8_000_000.0

    def test_skips_rows_with_missing_coords(self, t):
        rows = self.ROWS + [{"lon": "", "lat": "", "city": "Unknown", "pop": "0"}]
        m = AxisMapping(chart_type="symbol_map", x_column="lon", y_column="lat")
        result = t._transform_map(rows, m)
        assert len(result) == 2


# ── _transform_labeled ────────────────────────────────────────────────────────

class TestTransformLabeled:
    ROWS = [
        {"x": "10", "y": "200", "label": "Alpha"},
        {"x": "20", "y": "400", "label": "Beta"},
    ]

    def test_each_row_one_point(self, t):
        m = AxisMapping(x_column="x", y_column="y", label_column="label")
        result = t._transform_labeled(self.ROWS, m)
        assert len(result) == 2

    def test_label_preserved(self, t):
        m = AxisMapping(x_column="x", y_column="y", label_column="label")
        result = t._transform_labeled(self.ROWS, m)
        labels = {d["label"] for d in result}
        assert labels == {"Alpha", "Beta"}

    def test_x_converted_to_float_when_numeric(self, t):
        m = AxisMapping(x_column="x", y_column="y", label_column="label")
        result = t._transform_labeled(self.ROWS, m)
        assert result[0]["x"] == 10.0
