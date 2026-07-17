"""Authoritative, deterministic validation of chart-type feasibility.

This is the ONLY thing that decides whether a chart type can be built from a
dataset — it runs in the pipeline after every map/refine, independent of the LLM.
The prompt's requirement notes (CHART_REQUIREMENTS_NOTE) are advisory only: they
reduce how often a user hits an error, but correctness never depends on them.

Rules are declared per chart type in CHART_RULES. Each rule is a small, testable
callable ``(mapping, view) -> ValidationError | None``. Adding a chart type means
adding a registry entry, not editing a branchy function.
"""

from dataclasses import dataclass

from models import AxisMapping, Schema


# ── Result ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ValidationError:
    """A failed requirement: why it failed + what to do instead."""
    reason: str
    suggestion: str

    def __str__(self) -> str:
        return f"{self.reason}. {self.suggestion}"


# ── Schema view (typed helpers over the dataset's columns) ──────────────────────

class SchemaView:
    def __init__(self, schema: Schema):
        self._numeric = {c.name for c in schema.columns if c.type.value == "Float"}
        # strings and dates can both serve as a category / axis / grouping
        self.categorical = [c.name for c in schema.columns if c.type.value in ("String", "Date")]

    def is_numeric(self, col: str | None) -> bool:
        return bool(col) and col in self._numeric

    def is_categorical(self, col: str | None) -> bool:
        return bool(col) and col in set(self.categorical)

    def numeric_count(self) -> int:
        return len(self._numeric)

    def categorical_count(self) -> int:
        return len(self.categorical)


def _pretty(chart_type: str) -> str:
    return chart_type.replace("_", " ")


# ── Rules (each returns a ValidationError or None) ───────────────────────────────

def r_numeric_value_y(m: AxisMapping, v: SchemaView) -> ValidationError | None:
    if m.aggregation != "count" and not v.is_numeric(m.y_column):
        return ValidationError(
            f"A {_pretty(m.chart_type)} chart needs a numeric value column for the y-axis, "
            f"but '{m.y_column}' isn't numeric",
            "Pick a numeric column, or count rows instead.")
    return None


def r_numeric_xy(m: AxisMapping, v: SchemaView) -> ValidationError | None:
    if not (v.is_numeric(m.x_column) and v.is_numeric(m.y_column)):
        alt = "a bar chart or box plot" if v.is_categorical(m.x_column) else "a line chart"
        return ValidationError(
            f"A {_pretty(m.chart_type)} chart needs two numeric axes, but "
            f"'{m.x_column}'/'{m.y_column}' aren't both numeric",
            f"Try {alt} instead.")
    return None


def r_bubble_size(m: AxisMapping, v: SchemaView) -> ValidationError | None:
    if v.numeric_count() < 3 and not v.is_numeric(m.z_column):
        return ValidationError(
            f"A bubble chart needs a third numeric column to size the bubbles, but this data "
            f"has only {v.numeric_count()} numeric column(s)",
            "Try a scatter chart instead.")
    return None


def r_numeric_x(m: AxisMapping, v: SchemaView) -> ValidationError | None:
    if not v.is_numeric(m.x_column):
        return ValidationError(
            f"A histogram needs a numeric column to bin, but '{m.x_column}' is categorical",
            "Try a bar chart (counts per category) instead.")
    return None


def r_map_coords(m: AxisMapping, v: SchemaView) -> ValidationError | None:
    if not (v.is_numeric(m.x_column) and v.is_numeric(m.y_column)):
        return ValidationError(
            "A map needs numeric longitude and latitude columns, which this data doesn't have",
            "Try a bar or scatter chart instead.")
    return None


def r_two_distinct_categories(m: AxisMapping, v: SchemaView) -> ValidationError | None:
    # Both axes must be categorical (or date) AND different — a numeric axis
    # (e.g. price) can't serve as a heatmap axis or a network entity.
    both_categorical = v.is_categorical(m.x_column) and v.is_categorical(m.y_column)
    if not both_categorical or m.x_column == m.y_column:
        if m.chart_type == "heatmap":
            return ValidationError(
                "A heatmap needs two different categorical (or date) columns for its axes; "
                f"'{m.x_column}' and '{m.y_column}' don't qualify",
                "Try a bar chart instead.")
        return ValidationError(
            "A network graph needs two different categorical entity columns (source and target); "
            f"'{m.x_column}' and '{m.y_column}' don't qualify",
            "Try a bar chart instead.")
    return None


def r_stacking_group(m: AxisMapping, v: SchemaView) -> ValidationError | None:
    if not m.group_column:
        others = [c for c in v.categorical if c != m.x_column]
        if not others:
            base = "bar" if m.chart_type == "stacked_bar" else "area"
            return ValidationError(
                f"A {_pretty(m.chart_type)} chart needs a second categorical column to stack by, "
                f"but there isn't one",
                f"Try a {base} chart instead.")
    return None


def r_radar_metrics(m: AxisMapping, v: SchemaView) -> ValidationError | None:
    metrics = [mc for mc in (m.metric_columns or []) if v.is_numeric(mc)]
    long_form = bool(m.group_column) and v.is_numeric(m.y_column)
    if len(metrics) < 3 and not long_form and v.numeric_count() < 3:
        return ValidationError(
            f"A radar chart needs at least 3 numeric metrics to form the axes, "
            f"but this data has {v.numeric_count()}",
            "Try a bar or line chart instead.")
    return None


# ── Registry: chart type -> ordered rules it must satisfy ────────────────────────

_VALUE_CHARTS = ("bar", "line", "area", "pie", "box_plot", "violin")

CHART_RULES: dict[str, list] = {
    **{ct: [r_numeric_value_y] for ct in _VALUE_CHARTS},
    "stacked_bar":  [r_numeric_value_y, r_stacking_group],
    "stacked_area": [r_numeric_value_y, r_stacking_group],
    "scatter":      [r_numeric_xy],
    "bubble":       [r_numeric_xy, r_bubble_size],
    "histogram":    [r_numeric_x],
    "symbol_map":   [r_map_coords],
    "heatmap":      [r_two_distinct_categories],
    "network":      [r_two_distinct_categories],
    "radar":        [r_radar_metrics],
    "spider":       [r_radar_metrics],
}


class ChartValidator:
    """Runs the declared rules for a chart type against the dataset schema."""

    def __init__(self, rules: dict[str, list] | None = None):
        self._rules = rules if rules is not None else CHART_RULES

    def validate(self, mapping: AxisMapping, schema: Schema) -> ValidationError | None:
        """Return the first failed requirement, or None if the chart is buildable."""
        view = SchemaView(schema)
        for rule in self._rules.get(mapping.chart_type, ()):
            err = rule(mapping, view)
            if err is not None:
                return err
        return None


DEFAULT_VALIDATOR = ChartValidator()


def validate_chart(mapping: AxisMapping, schema: Schema) -> str | None:
    """Convenience wrapper: return the error message (str) or None."""
    err = DEFAULT_VALIDATOR.validate(mapping, schema)
    return str(err) if err is not None else None


# Advisory-only: injected into the refine prompt so the model tends to pick valid
# columns. Enforcement lives entirely in ChartValidator above — never here.
CHART_REQUIREMENTS_NOTE = (
    "Chart-type requirements (advisory — a validator enforces these regardless):\n"
    "- scatter/bubble: numeric x AND y (bubble also needs a numeric size column)\n"
    "- histogram: a numeric x_column to bin\n"
    "- box_plot/violin/bar/line/area/pie: a numeric y_column (the value)\n"
    "- stacked_bar/stacked_area: a group_column to stack by\n"
    "- heatmap/network: two DIFFERENT categorical columns (x_column != y_column)\n"
    "- radar/spider: 3+ numeric metric_columns (or long form: group_column + numeric y)\n"
    "- symbol_map: numeric longitude (x) and latitude (y)\n"
)
