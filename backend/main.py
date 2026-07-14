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


def run(csv_path: str, prompt: str, output: str, config: ChartConfig) -> None:
    print(f"Loading {csv_path!r}...")
    schema, rows = DataLoader().load(csv_path)
    for col in schema.columns:
        print(f"  {col.name} ({col.type.value})")

    print(f"\nMapping axes for: {prompt!r}")
    mapping = LLMMapper().map(schema, prompt)
    print(f"  x={mapping.x_column!r}  y={mapping.y_column!r}")

    data = Transformer().transform(rows, mapping)
    print(f"  {len(data)} data points")

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

    args = parser.parse_args()

    config = ChartConfig(
        title=args.title,
        x_label=args.x_label,
        y_label=args.y_label,
        color=args.color,
        palette=args.palette,
        y_format=args.y_format,
        curve=args.curve,
        show_area=not args.no_area,
    )

    run(args.csv, args.prompt, args.output, config)

    if args.open:
        subprocess.run(["open", args.output])


if __name__ == "__main__":
    main()
