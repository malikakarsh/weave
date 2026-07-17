from collections.abc import Callable

from models import AxisMapping, ChartConfig
from pipeline.data_loader import DataLoader
from pipeline.llm_mapper import LLMMapper
from pipeline.providers import LLMProvider
from pipeline.transformer import Transformer
from pipeline.templater import Templater


def _pretty(col: str) -> str:
    """Turn a snake_case or camelCase column name into a readable label."""
    if not col:
        return ""
    import re
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", col)
    return s.replace("_", " ").strip().title()


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

        config = config.model_copy(update={
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
            **({"svg_bg": mapping.background} if mapping.background else {}),
            **({"color": mapping.color} if mapping.color else {}),
            **({"category_colors": mapping.category_colors} if mapping.category_colors else {}),
        })

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
        _, rows = self._loader.load(csv_path)

        _emit("mapping")
        mapping = self._mapper.refine(current_mapping, history, instruction)

        config = config.model_copy(update={
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
            **({"svg_bg": mapping.background} if mapping.background else {}),
            **({"color": mapping.color} if mapping.color else {}),
            **({"category_colors": mapping.category_colors} if mapping.category_colors else {}),
        })

        _emit("transforming")
        data = self._transformer.transform(rows, mapping)

        _emit("rendering")
        html = self._templater.render(data, config)
        return html, mapping
