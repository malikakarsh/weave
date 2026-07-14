# Weave

Turn a CSV file and a plain-English prompt into an interactive D3.js chart — no code required.

```bash
python main.py data.csv "show me revenue over time" --open
```

## How it works

Weave runs a four-stage pipeline:

```
DataLoader → LLMMapper → Transformer → Templater
```

1. **DataLoader** — reads the CSV, auto-detects delimiter, infers column types (Date, Float, String), and validates that the dataset has at least one temporal and one numeric column.

2. **LLMMapper** — sends the schema and your prompt to Claude Haiku, which picks the best x-axis (Date), y-axis (Float), an optional group column for multi-line charts, and an optional filter if the user names specific groups.

3. **Transformer** — strips rows down to `{x, y}` pairs (single line) or `{group, values}` objects (multi-line). Missing values are kept as `null` so gaps are visible rather than silently dropped.

4. **Templater** — injects the data and a `ChartConfig` into a D3.js HTML template, producing a self-contained interactive chart.

## Output

A single `.html` file with:
- Single or multi-line chart with per-group colors and a legend
- Interactive hover — vertical line, dots on each series, tooltip showing all group values at that point
- Visible gaps where data is missing (no silent drops)
- **Copy SVG** — copies a static vector snapshot to clipboard (paste into Figma, web apps, PowerPoint on supported versions)
- **Download SVG** — saves an `.svg` file with all styles inlined; use Insert > Picture in PowerPoint for guaranteed vector quality

## Usage

```bash
cd backend
python main.py <csv> "<prompt>" [options]
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--output`, `-o` | `output.html` | Output file path |
| `--open` | off | Open chart in browser after generation |
| `--title` | — | Chart title |
| `--x-label` | — | X-axis label |
| `--y-label` | — | Y-axis label |
| `--color` | `#6366f1` | Line color for single-series charts (hex or named) |
| `--palette` | — | Space-separated colors for grouped charts (one per group) |
| `--y-format` | `,.0f` | D3 format string for y-axis ticks |
| `--curve` | `monotoneX` | Line curve: `monotoneX`, `linear`, `step`, `natural`, `cardinal` |
| `--no-area` | off | Hide the gradient area fill |

### Examples

Single line:
```bash
python main.py samples/sample.csv "show me Acme's revenue over time" \
  --title "Acme Revenue 2024" \
  --color "#10b981" \
  --y-format '$,.0f' \
  --open
```

Multi-line — all groups:
```bash
python main.py samples/sample.csv "compare revenue across all companies" \
  --title "Revenue by Company" \
  --y-label "Revenue (USD)" \
  --open
```

Multi-line — specific groups with custom colors:
```bash
python main.py samples/sample.csv "show Acme and Globex revenue over time" \
  --title "Acme vs Globex" \
  --palette "#6366f1" "#f59e0b" \
  --open
```

## Configuration

Copy `env.example` to `.env` and fill in your key:

```bash
cp env.example .env
```

```
ANTHROPIC_API_KEY=your_key_here
CLAUDE_MODEL=claude-haiku-4-5   # optional, this is the default
```

## Project structure

```
backend/
├── main.py                        # CLI entry point
├── models/
│   ├── schema.py                  # ColumnType, ColumnInfo, Schema
│   └── spec.py                    # AxisMapping, ChartConfig, PlotSpec
├── pipeline/
│   ├── data_loader.py             # CSV ingestion and type detection
│   ├── llm_mapper.py              # Claude Haiku axis selection
│   ├── prompts.py                 # System prompts
│   ├── transformer.py             # Row filtering to {x, y} pairs
│   ├── templater.py               # HTML rendering
│   └── templates/
│       └── line_chart.html        # D3.js line chart template
├── samples/
│   └── sample.csv                 # Example dataset
└── test_pipeline.py               # Manual end-to-end test
```

## What's next (V2)

- Orchestrator that decomposes a single prompt into multiple simultaneous plots
- Parallel plot rendering via `asyncio.gather()`
- More chart types (bar, scatter, area)
- Frontend UI — upload CSV, type prompt, see chart
