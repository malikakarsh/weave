import argparse
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from models import ChartConfig
from pipeline.data_loader import DataLoader
from pipeline.llm_mapper import LLMMapper
from pipeline.transformer import Transformer
from pipeline.templater import Templater


def run(csv_path: str, prompt: str, output: str, config: ChartConfig, sort_override: str | None = None) -> None:
    print(f"Loading {csv_path!r}...")
    schema, rows = DataLoader().load(csv_path)
    for col in schema.columns:
        print(f"  {col.name} ({col.type.value})")

    print(f"\nMapping axes for: {prompt!r}")
    mapping = LLMMapper().map(schema, prompt)
    if sort_override:
        mapping = mapping.model_copy(update={"sort_order": sort_override})
    print(f"  chart={mapping.chart_type!r}  x={mapping.x_column!r}  y={mapping.y_column!r}  "
          f"sort={mapping.sort_order!r}  time_unit={mapping.time_unit!r}")

    data = Transformer().transform(rows, mapping)
    print(f"  {len(data)} data points")

    # LLM chart type decision overrides default; explicit --curve/--color etc. still apply
    config = config.model_copy(update={"chart_type": mapping.chart_type})
    html = Templater().render(data, config)
    Path(output).write_text(html)
    print(f"\nChart written to {output!r}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="weave",
        description="Turn a CSV + prompt into an interactive D3 chart.",
    )

    parser.add_argument("csv",    help="Path to the CSV file")
    parser.add_argument("prompt", help="What you want to visualize, in plain English")

    parser.add_argument("--output", "-o", default="output.html",
                        help="Output HTML file (default: output.html)")
    parser.add_argument("--open", action="store_true",
                        help="Open the chart in the browser after generation")

    # ChartConfig flags
    parser.add_argument("--title",    default="",        help="Chart title")
    parser.add_argument("--x-label",  default="",        help="X-axis label")
    parser.add_argument("--y-label",  default="",        help="Y-axis label")
    parser.add_argument("--width",    type=int, default=836, help="Chart width in px (default: 836)")
    parser.add_argument("--height",   type=int, default=420, help="Chart height in px (default: 420)")
    parser.add_argument("--color",    default="#6366f1",
                        help="Line color for single-series charts (hex or named)")
    parser.add_argument("--palette",  nargs="+", metavar="COLOR",
                        help="Colors for grouped charts, one per group (e.g. --palette red blue green)")
    parser.add_argument("--y-format", default=",.0f",    help="D3 format string for y-axis ticks")
    parser.add_argument("--curve",    default="monotoneX",
                        choices=["monotoneX", "linear", "step", "natural", "cardinal"],
                        help="Line curve type")
    parser.add_argument("--no-area",  action="store_true",
                        help="Hide the gradient area fill")
    parser.add_argument("--svg-bg",   default="#1a1d27", metavar="COLOR",
                        help="SVG export background color (default: #1a1d27)")
    parser.add_argument("--sort",     default=None, choices=["asc", "desc", "none"],
                        help="Sort bar categories by y value: asc, desc, or none (default: LLM decides, usually asc)")

    args = parser.parse_args()

    config = ChartConfig(
        title=args.title,
        x_label=args.x_label,
        y_label=args.y_label,
        width=args.width,
        height=args.height,
        color=args.color,
        palette=args.palette,
        y_format=args.y_format,
        curve=args.curve,
        show_area=not args.no_area,
        svg_bg=args.svg_bg,
    )

    run(args.csv, args.prompt, args.output, config, sort_override=args.sort)

    if args.open:
        subprocess.run(["open", args.output])


if __name__ == "__main__":
    main()
