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

1. **DataLoader** — reads the CSV, auto-detects delimiter, infers column types (Date, Float, String), and validates that the dataset has at least one numeric column.

2. **LLMMapper** — sends the schema and your prompt to Claude Haiku, which decides the chart type (line, bar, scatter) and picks the x-axis, y-axis, an optional group column for multi-series charts, and an optional filter if the user names specific groups.

3. **Transformer** — strips rows down to `{x, y}` pairs (single series) or `{group, values}` objects (multi-series). Missing values are kept as `null` so gaps are visible rather than silently dropped.

4. **Templater** — injects the data and a `ChartConfig` into the matching D3.js template. Falls back to the line chart if the decided chart type doesn't have a template yet.

## Output

A single `.html` file with:
- Single or multi-series chart with per-group colors and a legend
- LLM-decided chart type — line for trends, bar for categories, scatter for two-numeric-axis relationships
- Interactive hover — vertical line, dots on each series, tooltip showing all group values at that point
- Visible gaps where data is missing (no silent drops)
- **Edit panel** — click Edit to reveal in-browser controls:
  - **SVG Background** — color picker that previews live and is used when exporting; axis/label/grid colors automatically flip between dark and light presets based on the background luminance so text stays readable on any background
  - **Chart Size** — − / + buttons to resize the chart
  - **Bar Width** — − / + buttons to adjust bar spacing (bar chart only)
  - **Title / X Label / Y Label** — text inputs to add or change labels live
  - **Click a bar or line** to change its color; in grouped charts, changing one bar/line recolors the whole series; clicking empty space restores all series to full opacity
- **Copy SVG** — copies a static vector snapshot to clipboard; works on `file://` via `execCommand` fallback and on `http://` via the Clipboard API
- **Download SVG** — saves an `.svg` file with all styles inlined; use Insert > Picture in PowerPoint for guaranteed vector quality
- `--svg-bg COLOR` — bake a custom SVG export background into the file at generation time (default: `#1a1d27`)

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
| `--width` | `836` | Initial chart width in px |
| `--height` | `420` | Initial chart height in px |
| `--color` | `#6366f1` | Line color for single-series charts (hex or named) |
| `--palette` | — | Space-separated colors for grouped charts (one per group) |
| `--y-format` | `,.0f` | D3 format string for y-axis ticks |
| `--curve` | `monotoneX` | Line curve: `monotoneX`, `linear`, `step`, `natural`, `cardinal` |
| `--no-area` | off | Hide the gradient area fill |
| `--svg-bg` | `#1a1d27` | SVG export background color |

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

Non-temporal x-axis:
```bash
python main.py samples/numeric_x.csv "show how income changes with age" --open
```

Bar chart — total per category:
```bash
python main.py samples/sample.csv "show total revenue per company" \
  --title "Revenue by Company" \
  --color "#6366f1" \
  --open
```

Grouped bar chart — side-by-side bars per group:
```bash
python main.py samples/sample.csv "compare monthly revenue for each company as grouped bars" \
  --title "Monthly Revenue by Company" \
  --open
```

Scatter chart — two numeric axes:
```bash
python main.py samples/numeric_x.csv "show how income changes with age as a scatter plot" \
  --title "Age vs Income" \
  --x-label "Age" \
  --y-label "Income" \
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
│       ├── line_chart.html        # D3.js line chart template
│       ├── bar_chart.html         # D3.js bar chart (flat + grouped)
│       └── scatter_chart.html     # D3.js scatter chart
├── samples/
│   ├── sample.csv                 # Multi-company revenue dataset (Date x-axis)
│   └── numeric_x.csv              # Age vs income dataset (Float x-axis)
└── test_pipeline.py               # Manual end-to-end test
```

## What's next (V2)

**Chart types**
- Pie / donut chart

**API + UI**
- FastAPI backend — `POST /chart`, `GET /health`
- Frontend — file upload + prompt input + rendered chart in browser
- Deployed with a live URL (Railway / Render / Fly.io)

**Test suite**
- pytest coverage for DataLoader, Transformer, and LLMMapper

**Multi-plot**
- Orchestrator that decomposes a single prompt into N plot specs
- Parallel rendering via `asyncio.gather()`

**Data storytelling**
- Intelligent peer selection — when a user focuses on one entity (e.g. "compare Microsoft"), the LLM picks 4-5 structurally similar peers based on revenue scale, sector, and growth trajectory rather than requiring the user to name them
- Two-tier visual hierarchy — focus group gets distinct colors and full opacity; the rest render in a single muted color at low opacity so they provide context without cluttering the chart
- Pre-aggregation stage (`Summarizer`) that computes per-group stats (mean, CAGR, magnitude) before the LLM call, keeping token usage manageable even on large datasets like Fortune 500
