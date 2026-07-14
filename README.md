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

2. **LLMMapper** — sends the schema and your prompt to Claude Haiku, which picks the best x-axis (Date) and y-axis (Float) columns for the visualization.

3. **Transformer** — strips the raw rows down to just `{x, y}` pairs for the chosen columns. Missing values are kept as `null` so gaps are visible in the chart rather than silently dropped.

4. **Templater** — injects the data and a `ChartConfig` into a D3.js HTML template, producing a self-contained interactive chart.

## Output

A single `.html` file with:
- Interactive line chart with hover tooltips
- Visible gaps where data is missing (no silent drops)
- **Copy SVG** — copies a static vector snapshot to clipboard (paste into Figma, web apps, PowerPoint on supported versions)
- **Download SVG** — saves an `.svg` file; use Insert > Picture in PowerPoint for guaranteed vector quality

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
| `--color` | `#6366f1` | Line color (hex) |
| `--y-format` | `,.0f` | D3 format string for y-axis ticks |
| `--curve` | `monotoneX` | Line curve: `monotoneX`, `linear`, `step`, `natural`, `cardinal` |
| `--no-area` | off | Hide the gradient area fill |

### Example

```bash
python main.py samples/sample.csv "show me revenue over time" \
  --title "Monthly Revenue 2024" \
  --x-label "Month" \
  --y-label "Revenue (USD)" \
  --color "#10b981" \
  --y-format "$,.0f" \
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
