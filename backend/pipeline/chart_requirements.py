"""Authoritative, deterministic validation of chart-type feasibility.

This is the ONLY thing that decides whether a chart type can be built from a
dataset — it runs in the pipeline after every map/refine, independent of the LLM.
The prompt's requirement notes (CHART_REQUIREMENTS_NOTE) are advisory only: they
reduce how often a user hits an error, but correctness never depends on them.

Rules are declared per chart type in CHART_RULES. Each rule is a small, testable
callable ``(mapping, view) -> str | None`` returning a failure *reason*. The
suggested alternative is NOT hardcoded — the validator computes which chart types
actually validate against the same columns and suggests one of those.
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


# ── Rules — each returns a failure reason (str) or None ──────────────────────────

def r_numeric_value_y(m: AxisMapping, v: SchemaView) -> str | None:
    if m.aggregation != "count" and not v.is_numeric(m.y_column):
        return (f"A {_pretty(m.chart_type)} chart needs a numeric value column for the y-axis, "
                f"but '{m.y_column}' isn't numeric")
    return None


def r_numeric_xy(m: AxisMapping, v: SchemaView) -> str | None:
    if not (v.is_numeric(m.x_column) and v.is_numeric(m.y_column)):
        return (f"A {_pretty(m.chart_type)} chart needs two numeric axes, but "
                f"'{m.x_column}'/'{m.y_column}' aren't both numeric")
    return None


def r_bubble_size(m: AxisMapping, v: SchemaView) -> str | None:
    if v.numeric_count() < 3 and not v.is_numeric(m.z_column):
        return (f"A bubble chart needs a third numeric column to size the bubbles, but this data "
                f"has only {v.numeric_count()} numeric column(s)")
    return None


def r_numeric_x(m: AxisMapping, v: SchemaView) -> str | None:
    if not v.is_numeric(m.x_column):
        return f"A histogram needs a numeric column to bin, but '{m.x_column}' is categorical"
    return None


def r_map_coords(m: AxisMapping, v: SchemaView) -> str | None:
    if not (v.is_numeric(m.x_column) and v.is_numeric(m.y_column)):
        return "A map needs numeric longitude and latitude columns, which this data doesn't have"
    return None


def r_heatmap_axes(m: AxisMapping, v: SchemaView) -> str | None:
    # Two categorical axes → matrix heatmap; two numeric axes → binned density
    # heatmap. A mix (one category + one numeric) isn't supported.
    if m.x_column == m.y_column:
        return "A heatmap needs two different columns for its axes"
    both_categorical = v.is_categorical(m.x_column) and v.is_categorical(m.y_column)
    both_numeric = v.is_numeric(m.x_column) and v.is_numeric(m.y_column)
    if not (both_categorical or both_numeric):
        return ("A heatmap needs two categorical axes (a matrix) or two numeric axes (a density map); "
                f"'{m.x_column}' and '{m.y_column}' are a mix")
    return None


def r_network_entities(m: AxisMapping, v: SchemaView) -> str | None:
    both_categorical = v.is_categorical(m.x_column) and v.is_categorical(m.y_column)
    if not both_categorical or m.x_column == m.y_column:
        return ("A network graph needs two different categorical entity columns (source and target); "
                f"'{m.x_column}' and '{m.y_column}' don't qualify")
    return None


def r_stacking_group(m: AxisMapping, v: SchemaView) -> str | None:
    if not m.group_column:
        others = [c for c in v.categorical if c != m.x_column]
        if not others:
            return (f"A {_pretty(m.chart_type)} chart needs a second categorical column to stack by, "
                    f"but there isn't one")
    return None


def r_radar_metrics(m: AxisMapping, v: SchemaView) -> str | None:
    # Radar needs its axes named in the MAPPING: either 3+ numeric metric_columns
    # (wide form) or a group_column plus a numeric y (long form). The dataset
    # merely *having* numeric columns isn't enough — without metric_columns the
    # transform degenerates to a flat chart, so radar must not validate (or be
    # suggested) on categorical x/y just because other numeric columns exist.
    metrics = [mc for mc in (m.metric_columns or []) if v.is_numeric(mc)]
    long_form = bool(m.group_column) and v.is_numeric(m.y_column)
    if len(metrics) < 3 and not long_form:
        if v.numeric_count() < 3:
            return (f"A radar chart needs at least 3 numeric metrics to form the axes, "
                    f"but this data has {v.numeric_count()}")
        return ("A radar chart needs 3+ numeric metric columns (or a group column with a "
                "numeric value); this chart's columns don't provide them")
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
    "heatmap":      [r_heatmap_axes],
    "network":      [r_network_entities],
    "radar":        [r_radar_metrics],
    "spider":       [r_radar_metrics],
}

# Order in which alternatives are offered when a chart is rejected — simple,
# broadly-applicable types first.
_SUGGEST_ORDER = ("bar", "box_plot", "line", "area", "scatter", "histogram",
                  "violin", "pie", "heatmap", "radar")


class ChartValidator:
    """Runs the declared rules for a chart type against the dataset schema, and
    suggests only chart types that would actually validate on the same columns."""

    def __init__(self, rules: dict[str, list] | None = None):
        self._rules = rules if rules is not None else CHART_RULES

    def _reason(self, mapping: AxisMapping, view: SchemaView) -> str | None:
        for rule in self._rules.get(mapping.chart_type, ()):
            reason = rule(mapping, view)
            if reason is not None:
                return reason
        return None

    def valid_alternatives(self, mapping: AxisMapping, schema: Schema) -> list[str]:
        """Chart types (other than the requested one) that pass validation with
        the CURRENT columns — i.e. actually-switchable alternatives."""
        view = SchemaView(schema)
        return [ct for ct in _SUGGEST_ORDER
                if ct != mapping.chart_type
                and self._reason(mapping.model_copy(update={"chart_type": ct}), view) is None]

    def validate(self, mapping: AxisMapping, schema: Schema) -> ValidationError | None:
        """Return the first failed requirement (with a validated suggestion) or None."""
        view = SchemaView(schema)
        reason = self._reason(mapping, view)
        if reason is None:
            return None
        alts = self.valid_alternatives(mapping, schema)
        if alts:
            names = " or ".join(_pretty(a) for a in alts[:2])
            suggestion = f"Try a {names} instead."
        else:
            suggestion = "No standard chart fits these columns — try different columns."
        return ValidationError(reason, suggestion)


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
    "- heatmap: two DIFFERENT categorical columns (matrix) OR two DIFFERENT numeric columns (density); not a mix\n"
    "- network: two DIFFERENT categorical entity columns (x_column != y_column)\n"
    "- radar/spider: 3+ numeric metric_columns (or long form: group_column + numeric y)\n"
    "- symbol_map: numeric longitude (x) and latitude (y)\n"
)
