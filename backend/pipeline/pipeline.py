import re
from collections.abc import Callable

from models import AxisMapping, ChartConfig
from models.spec import ControlSpec
from pipeline.data_loader import DataLoader
from pipeline.llm_mapper import LLMMapper
from pipeline.providers import LLMProvider
from pipeline.transformer import Transformer
from pipeline.templater import Templater
from pipeline.palettes import resolve_palette
from pipeline.chart_requirements import validate_chart
from pipeline.category_resolver import (
    resolve_references, apply_choice, ClarificationNeeded,
)


def _ensure_non_empty(data) -> None:
    """Raise a clear error instead of rendering a blank chart when the transform
    produced no data — usually a filter that matched nothing or columns that came
    out empty."""
    empty = (not data.get("nodes")) if isinstance(data, dict) else (not data)
    if empty:
        raise ValueError(
            "No data to plot — the filters or selected columns produced an empty "
            "result. Try removing a filter (e.g. a year), or run “show columns” "
            "to check the exact column names."
        )


def _pretty(col: str) -> str:
    """Turn a snake_case or camelCase column name into a readable label."""
    if not col:
        return ""
    import re
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", col)
    return s.replace("_", " ").strip().title()


def _promote_threshold_filter(mapping: AxisMapping, instruction: str) -> AxisMapping:
    """When the user asks for an INTERACTIVE min/max filter/slider with no explicit
    number (e.g. 'add a maximum sepal width filter') but the model emitted a hard
    `filters` threshold instead, promote it to a `controls` slider. A hard filter
    with a guessed cutoff can wipe the chart to empty; a slider is bounded by the
    data and starts non-filtering. A threshold with an EXPLICIT number (which shows
    up as a digit in the instruction) is left as a real filter."""
    instr = instruction.lower()
    slider_intent = (
        ("slider" in instr
         or ("filter" in instr and re.search(r"\b(min|max|minimum|maximum)\b", instr)))
        and not re.search(r"\d", instr)          # an explicit number ⇒ a real hard filter
    )
    if not slider_intent or not mapping.filters:
        return mapping

    existing = {(c.column, c.kind) for c in (mapping.controls or [])}
    new_controls = list(mapping.controls or [])
    keep_filters = []
    for f in mapping.filters:
        if not f.values and (f.min is not None or f.max is not None):
            if f.min is not None and (f.column, "min") not in existing:
                new_controls.append(ControlSpec(column=f.column, kind="min"))
            if f.max is not None and (f.column, "max") not in existing:
                new_controls.append(ControlSpec(column=f.column, kind="max"))
        else:
            keep_filters.append(f)
    if len(keep_filters) == len(mapping.filters):
        return mapping                            # nothing promoted
    return mapping.model_copy(update={
        "filters": keep_filters or None,
        "controls": new_controls or None,
    })


def _missing_column(mapping: AxisMapping, schema) -> str | None:
    """A user-facing error if the mapping references a column that isn't in the
    data (e.g. the instruction named a column that doesn't exist), else None."""
    names = {c.name for c in schema.columns}
    roles = [
        ("x-axis", mapping.x_column), ("y-axis", mapping.y_column),
        ("group", mapping.group_column), ("size", mapping.z_column),
        ("label", mapping.label_column),
    ]
    for role, col in roles:
        if col and col not in names:
            avail = ", ".join(c.name for c in schema.columns)
            return f"There's no '{col}' column to use for the {role}. Available columns: {avail}."
    for col in (mapping.metric_columns or []):
        if col not in names:
            avail = ", ".join(c.name for c in schema.columns)
            return f"There's no '{col}' column in your data. Available columns: {avail}."
    return None


def _keep_axes_on_type_change(mapping: AxisMapping, current: AxisMapping, instruction: str) -> AxisMapping:
    """Restore x/y columns the user didn't explicitly name, so a chart-type change
    can't silently swap axes to sneak past validation."""
    import re
    instr = instruction.lower()
    def named(col: str | None) -> bool:
        return bool(col) and re.search(rf"\b{re.escape(col.lower())}\b", instr) is not None
    updates = {}
    for field in ("x_column", "y_column"):
        new_col = getattr(mapping, field)
        old_col = getattr(current, field)
        if new_col != old_col and not named(new_col):
            updates[field] = old_col
    return mapping.model_copy(update=updates) if updates else mapping


def _apply_mapping(config: ChartConfig, mapping: AxisMapping) -> ChartConfig:
    """Fold an AxisMapping into a ChartConfig, returning the updated config."""
    palette = resolve_palette(mapping.palette)
    update: dict = {
        "chart_type":      mapping.chart_type,
        "facet_direction": mapping.facet_direction,
        "facet_free_y":    mapping.facet_free_y,
        "title":           mapping.title or config.title,
        "x_label":         mapping.x_label or config.x_label or _pretty(mapping.x_column),
        "y_label":         mapping.y_label or config.y_label or _pretty(mapping.y_column),
        "z_label":         mapping.z_column or config.z_label,
        "x_column":        mapping.x_column or config.x_column,
        "y_column":        mapping.y_column or config.y_column,
        "background":      mapping.background or config.background,
    }
    if mapping.background:
        update["svg_bg"] = mapping.background
    if mapping.category_colors:
        update["category_colors"] = mapping.category_colors
    if mapping.group_labels:
        update["group_labels"] = mapping.group_labels
    if mapping.mark_scale is not None:
        update["mark_scale"] = max(0.2, min(mapping.mark_scale, 4.0))
    if palette:
        update["palette"] = palette
    # Color precedence: an explicit color wins; otherwise a named palette also
    # drives the single-series (unicolor) color from its first shade, so
    # "dark palette" / "light palette" work on non-grouped charts too.
    if mapping.color:
        update["color"] = mapping.color
    elif palette:
        update["color"] = palette[0]
    return config.model_copy(update=update)


class Pipeline:
    """Orchestrates DataLoader → LLMMapper → Transformer → Templater."""

    def __init__(self, provider: LLMProvider | None = None):
        self._loader = DataLoader()
        self._mapper = LLMMapper(provider)
        self._transformer = Transformer()
        self._templater = Templater()

    def run(
        self,
        csv_path: str,
        prompt: str,
        config: ChartConfig,
        sort_override: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> tuple[str, AxisMapping]:
        """
        Run the full pipeline and return (html, mapping).
        Raises on any stage failure — no side effects (no printing, no file I/O).
        on_progress(stage) is called before each stage: loading, mapping, transforming, rendering.
        """
        def _emit(stage: str) -> None:
            if on_progress:
                on_progress(stage)

        _emit("loading")
        schema, rows = self._loader.load(csv_path)

        _emit("mapping")
        mapping = self._mapper.map(schema, prompt)
        if sort_override:
            mapping = mapping.model_copy(update={"sort_order": sort_override})

        err = validate_chart(mapping, schema)
        if err:
            raise ValueError(err)

        # Resolve referenced category values against the data. On generation we
        # auto-pick the closest candidate for any ambiguity (no interactive gate).
        resolved = resolve_references(mapping, rows)
        mapping = resolved.mapping
        for clar in resolved.clarifications:
            if clar.options:
                mapping = apply_choice(mapping, clar, clar.options[0])

        config = _apply_mapping(config, mapping)

        _emit("transforming")
        data, controls = self._transform_and_controls(rows, mapping)
        _ensure_non_empty(data)

        _emit("rendering")
        html = self._templater.render(data, config, controls)

        return html, mapping

    def refine(
        self,
        csv_path: str,
        current_mapping: AxisMapping,
        history: list[dict],
        instruction: str,
        config: ChartConfig,
        on_progress: Callable[[str], None] | None = None,
    ) -> tuple[str, AxisMapping]:
        """Apply a refinement instruction to an existing mapping and re-render."""
        def _emit(stage: str) -> None:
            if on_progress:
                on_progress(stage)

        _emit("loading")
        schema, rows = self._loader.load(csv_path)

        _emit("mapping")
        mapping = self._mapper.refine(current_mapping, history, instruction, schema)

        # Guard against the LLM silently swapping the axes to satisfy a new chart
        # type's requirements. On a pure type change, restore any x/y column the
        # user didn't explicitly name, so validation reflects the real axes.
        if mapping.chart_type != current_mapping.chart_type:
            mapping = _keep_axes_on_type_change(mapping, current_mapping, instruction)

        # A bare "min/max <col> filter/slider" is interactive — if the model made it
        # a hard filter (which can empty the chart), turn it back into a slider.
        mapping = _promote_threshold_filter(mapping, instruction)

        err = _missing_column(mapping, schema) or validate_chart(mapping, schema)
        if err:
            raise ValueError(err)

        # Resolve referenced category values; ambiguous/unknown ones become a
        # human-in-the-loop clarification instead of a silent best guess.
        resolved = resolve_references(mapping, rows)
        if resolved.clarifications:
            raise ClarificationNeeded(resolved.mapping, resolved.clarifications)
        mapping = resolved.mapping

        # No-op guard: if the instruction produced no change to the mapping, the
        # model couldn't map it to a supported edit (commonly a column/value name
        # that isn't in the data). Surface that instead of silently re-rendering
        # the identical chart, which reads as "nothing happened".
        if mapping.model_dump() == current_mapping.model_dump():
            raise ValueError(
                "Couldn't apply that change — the chart is unchanged. "
                "Check that any column or value names in your instruction match your data."
            )

        config = _apply_mapping(config, mapping)

        _emit("transforming")
        data, controls = self._transform_and_controls(rows, mapping)
        _ensure_non_empty(data)

        _emit("rendering")
        html = self._templater.render(data, config, controls)
        return html, mapping

    def _transform_and_controls(self, rows, mapping):
        """Transform + (optionally) build the interactive-control payload. When a
        `scrub` control exists the rendered data is its default pre-built slice, so
        the chart opens on a valid view and the slider swaps slices client-side."""
        controls = self._transformer.build_control_payload(rows, mapping)
        if controls and controls.get("default") is not None:
            data = controls["slices"].get(controls["default"], [])
        else:
            data = self._transformer.transform(rows, mapping)
        return data, controls

    def render_mapping(
        self,
        csv_path: str,
        mapping: AxisMapping,
        config: ChartConfig,
    ) -> tuple[str, AxisMapping]:
        """Render a fully-resolved mapping with no LLM call — used to apply a
        user's clarification choices."""
        schema, rows = self._loader.load(csv_path)
        err = validate_chart(mapping, schema)
        if err:
            raise ValueError(err)
        resolved = resolve_references(mapping, rows)
        mapping = resolved.mapping
        for clar in resolved.clarifications:
            if clar.options:
                mapping = apply_choice(mapping, clar, clar.options[0])
        config = _apply_mapping(config, mapping)
        data, controls = self._transform_and_controls(rows, mapping)
        html = self._templater.render(data, config, controls)
        return html, mapping
