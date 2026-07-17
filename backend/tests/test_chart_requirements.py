import pytest

from models import AxisMapping, ColumnInfo, ColumnType, Schema
from pipeline.chart_requirements import (
    ChartValidator,
    ValidationError,
    validate_chart,
)


def schema(*cols: tuple[str, ColumnType]) -> Schema:
    return Schema(
        row_count=100,
        columns=[ColumnInfo(name=n, type=t, sample=["1"]) for n, t in cols],
    )


# A dataset with a category + several numeric columns (iris-like).
IRIS = schema(
    ("Species", ColumnType.STRING),
    ("SepalLengthCm", ColumnType.FLOAT),
    ("SepalWidthCm", ColumnType.FLOAT),
    ("PetalLengthCm", ColumnType.FLOAT),
    ("PetalWidthCm", ColumnType.FLOAT),
)

# A dataset with two categories + one numeric (diamonds-like subset).
DIA = schema(
    ("cut", ColumnType.STRING),
    ("color", ColumnType.STRING),
    ("price", ColumnType.FLOAT),
)


def mapping(**kw) -> AxisMapping:
    d = dict(x_column="Species", y_column="SepalLengthCm", aggregation="mean")
    d.update(kw)
    return AxisMapping(**d)


class TestInvalid:
    def test_network_needs_two_entities(self):
        assert validate_chart(mapping(chart_type="network", x_column="Species", y_column="Species"), IRIS)
        # only one categorical column available
        assert validate_chart(mapping(chart_type="network", y_column="SepalLengthCm"), IRIS)

    def test_heatmap_needs_two_categories(self):
        assert validate_chart(mapping(chart_type="heatmap", y_column="PetalLengthCm"), IRIS)

    def test_network_rejects_numeric_axis_even_with_other_categories(self):
        # DIA has cut/color categoricals, but the actual axes are cut (cat) + price (numeric)
        assert validate_chart(mapping(chart_type="network", x_column="cut", y_column="price"), DIA)

    def test_heatmap_rejects_numeric_axis(self):
        assert validate_chart(mapping(chart_type="heatmap", x_column="cut", y_column="price"), DIA)

    def test_histogram_needs_numeric_x(self):
        assert validate_chart(mapping(chart_type="histogram", x_column="Species"), IRIS)

    def test_scatter_needs_numeric_axes(self):
        assert validate_chart(mapping(chart_type="scatter", x_column="cut", y_column="price"), DIA)

    def test_bubble_needs_three_numeric(self):
        assert validate_chart(mapping(chart_type="bubble", x_column="price", y_column="price"), DIA)

    def test_radar_needs_three_metrics(self):
        assert validate_chart(mapping(chart_type="radar", x_column="cut", y_column="price"), DIA)

    def test_value_chart_needs_numeric_y(self):
        assert validate_chart(mapping(chart_type="bar", y_column="Species", aggregation="mean"), IRIS)

    def test_map_needs_numeric_coords(self):
        assert validate_chart(mapping(chart_type="symbol_map", x_column="Species", y_column="SepalLengthCm"), IRIS)


class TestValid:
    def test_bar(self):
        assert validate_chart(mapping(chart_type="bar"), IRIS) is None

    def test_bar_count_allows_categorical_y(self):
        assert validate_chart(mapping(chart_type="bar", y_column="Species", aggregation="count"), IRIS) is None

    def test_scatter_numeric(self):
        assert validate_chart(mapping(chart_type="scatter", x_column="SepalLengthCm", y_column="SepalWidthCm"), IRIS) is None

    def test_histogram_numeric(self):
        assert validate_chart(mapping(chart_type="histogram", x_column="PetalLengthCm"), IRIS) is None

    def test_radar_wide(self):
        assert validate_chart(mapping(
            chart_type="radar",
            metric_columns=["SepalLengthCm", "SepalWidthCm", "PetalLengthCm"],
        ), IRIS) is None

    def test_heatmap_two_categories(self):
        m = AxisMapping(chart_type="heatmap", x_column="cut", y_column="color", aggregation="count")
        assert validate_chart(m, DIA) is None

    def test_bubble_three_numeric(self):
        assert validate_chart(mapping(chart_type="bubble", x_column="SepalLengthCm", y_column="SepalWidthCm", z_column="PetalLengthCm"), IRIS) is None


class TestValidatorClass:
    def test_returns_structured_error_with_suggestion(self):
        err = ChartValidator().validate(mapping(chart_type="histogram", x_column="Species"), IRIS)
        assert isinstance(err, ValidationError)
        assert "numeric" in err.reason.lower()
        assert err.suggestion            # a non-empty suggestion clause
        assert str(err).endswith(err.suggestion)

    def test_valid_returns_none(self):
        assert ChartValidator().validate(mapping(chart_type="bar"), IRIS) is None

    def test_unknown_chart_type_has_no_rules(self):
        # a type with no declared rules is treated as buildable
        assert ChartValidator().validate(mapping(chart_type="treemap"), IRIS) is None

    def test_injectable_rules(self):
        # the registry is injectable, so rules are testable in isolation
        always_fail = lambda m, v: ValidationError("nope", "Try something else.")
        v = ChartValidator({"bar": [always_fail]})
        assert v.validate(mapping(chart_type="bar"), IRIS).reason == "nope"
