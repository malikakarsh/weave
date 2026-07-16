import argparse
import subprocess
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from models import ChartConfig
from pipeline.pipeline import Pipeline
from pipeline.providers import get_provider


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

    # Provider flags
    parser.add_argument("--provider", default=None,
                        choices=["anthropic", "ollama", "gemini"],
                        help="LLM provider (default: LLM_PROVIDER env var or 'anthropic')")
    parser.add_argument("--model", default=None,
                        help="Model override (e.g. claude-haiku-4-5, llama3.2, gemini-2.0-flash)")

    # ChartConfig flags
    parser.add_argument("--title",    default="",        help="Chart title")
    parser.add_argument("--x-label",  default="",        help="X-axis label")
    parser.add_argument("--y-label",  default="",        help="Y-axis label")
    parser.add_argument("--width",    type=int, default=836, help="Chart width in px (default: 836)")
    parser.add_argument("--height",   type=int, default=420, help="Chart height in px (default: 420)")
    parser.add_argument("--color",    default="#6366f1",
                        help="Line color for single-series charts (hex or named)")
    parser.add_argument("--palette",  nargs="+", metavar="COLOR",
                        help="Colors for grouped charts, one per group")
    parser.add_argument("--y-format", default=",.0f",    help="D3 format string for y-axis ticks")
    parser.add_argument("--curve",    default="monotoneX",
                        choices=["monotoneX", "linear", "step", "natural", "cardinal"],
                        help="Line curve type")
    parser.add_argument("--no-area",  action="store_true",
                        help="Hide the gradient area fill")
    parser.add_argument("--svg-bg",   default="#1a1d27", metavar="COLOR",
                        help="SVG export background color (default: #1a1d27)")
    parser.add_argument("--sort",     default=None, choices=["asc", "desc", "none"],
                        help="Sort bar categories by y value: asc, desc, or none")

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

    provider = get_provider(args.provider, args.model)
    pipeline = Pipeline(provider)

    print(f"Loading {args.csv!r}...")
    print(f"Mapping via {type(provider).__name__} ({provider.model}): {args.prompt!r}")

    html, mapping = pipeline.run(args.csv, args.prompt, config, sort_override=args.sort)

    print(f"  chart={mapping.chart_type!r}  x={mapping.x_column!r}  y={mapping.y_column!r}  "
          f"group={mapping.group_column!r}  agg={mapping.aggregation!r}  "
          f"top_n={mapping.top_n!r}  sort={mapping.sort_order!r}  "
          f"time_unit={mapping.time_unit!r}  x_min={mapping.x_min!r}  x_max={mapping.x_max!r}")

    Path(args.output).write_text(html)
    print(f"Chart written to {args.output!r}")

    if args.open:
        subprocess.run(["open", args.output])


if __name__ == "__main__":
    main()
