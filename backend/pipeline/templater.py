import json
from pathlib import Path

from models import ChartConfig

TEMPLATES_DIR = Path(__file__).parent / "templates"


class Templater:
    def __init__(self, templates_dir: Path = TEMPLATES_DIR):
        self._templates_dir = templates_dir

    def render(self, data: list[dict], config: ChartConfig = ChartConfig()) -> str:
        template_path = self._templates_dir / f"{config.chart_type}_chart.html"
        template = template_path.read_text()
        return (
            template
            .replace("__DATA__", json.dumps(data))
            .replace("__CONFIG__", json.dumps(config.model_dump()))
        )
