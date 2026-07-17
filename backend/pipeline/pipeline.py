from collections.abc import Callable

from models import AxisMapping, ChartConfig
from pipeline.data_loader import DataLoader
from pipeline.llm_mapper import LLMMapper
from pipeline.providers import LLMProvider
from pipeline.transformer import Transformer
from pipeline.templater import Templater
from pipeline.palettes import resolve_palette
from pipeline.chart_requirements import validate_chart


def _pretty(col: str) -> str:
    """Turn a snake_case or camelCase column name into a readable label."""
    if not col:
        return ""
    import re
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", col)
    return s.replace("_", " ").strip().title()


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

        config = _apply_mapping(config, mapping)

        _emit("transforming")
        data = self._transformer.transform(rows, mapping)

        _emit("rendering")
        html = self._templater.render(data, config)

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

        err = validate_chart(mapping, schema)
        if err:
            raise ValueError(err)

        config = _apply_mapping(config, mapping)

        _emit("transforming")
        data = self._transformer.transform(rows, mapping)

        _emit("rendering")
        html = self._templater.render(data, config)
        return html, mapping
