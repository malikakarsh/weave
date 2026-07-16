from models import AxisMapping, ChartConfig
from pipeline.data_loader import DataLoader
from pipeline.llm_mapper import LLMMapper
from pipeline.providers import LLMProvider
from pipeline.transformer import Transformer
from pipeline.templater import Templater


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
    ) -> tuple[str, AxisMapping]:
        """
        Run the full pipeline and return (html, mapping).
        Raises on any stage failure — no side effects (no printing, no file I/O).
        """
        schema, rows = self._loader.load(csv_path)

        mapping = self._mapper.map(schema, prompt)
        if sort_override:
            mapping = mapping.model_copy(update={"sort_order": sort_override})

        config = config.model_copy(update={
            "chart_type":      mapping.chart_type,
            "facet_direction": mapping.facet_direction,
            "facet_free_y":    mapping.facet_free_y,
            "title":           mapping.title or config.title,
            "x_label":         mapping.x_label or config.x_label,
            "y_label":         mapping.y_label or config.y_label,
        })

        data = self._transformer.transform(rows, mapping)
        html = self._templater.render(data, config)

        return html, mapping

    def refine(
        self,
        csv_path: str,
        current_mapping: AxisMapping,
        history: list[dict],
        instruction: str,
        config: ChartConfig,
    ) -> tuple[str, AxisMapping]:
        """Apply a refinement instruction to an existing mapping and re-render."""
        _, rows = self._loader.load(csv_path)

        mapping = self._mapper.refine(current_mapping, history, instruction)

        config = config.model_copy(update={
            "chart_type":      mapping.chart_type,
            "facet_direction": mapping.facet_direction,
            "facet_free_y":    mapping.facet_free_y,
            "title":           mapping.title or config.title,
            "x_label":         mapping.x_label or config.x_label,
            "y_label":         mapping.y_label or config.y_label,
        })

        data = self._transformer.transform(rows, mapping)
        html = self._templater.render(data, config)
        return html, mapping
