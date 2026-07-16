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

2. **LLMMapper** — sends the schema and your prompt to Claude, which decides the chart type (line, area, bar, pie, bubble, scatter, heatmap, network), picks the x/y/group/z/label columns, chooses an aggregation function (sum/mean/count/min/max) based on intent words in the prompt, optionally limits to the top N groups by aggregated value, sets a time unit (year/month/day) when the prompt asks for period-level bucketing of date columns, and applies x_min/x_max bounds for time period filtering.

3. **Transformer** — routes to one of five transform modes based on the mapping:
   - **flat** — aggregates rows by x into `{x, y}` pairs (single series)
   - **grouped** — aggregates by (group, x) into `{group, values}` objects (multi-series)
   - **labeled** — one point per row with no aggregation; `{x, y, z, label}` (bubble with named items)
   - **heatmap** — aggregates by (x_column, y_column) cell into `{x, y, z}` pairs
   - **network** — aggregates edges by (source, target) into `{nodes, links}` with per-node weight sums

   Date x-values are optionally truncated to a period (year → `2024-01-01`, month → `2024-03-01`, day → `2024-03-15`) before bucketing. Missing values are kept as `null` so gaps are visible rather than silently dropped.

4. **Templater** — injects the data and a `ChartConfig` into the matching D3.js template.

## Chart types

| Type | Best for | Key columns |
|---|---|---|
| `line` | Trends over time or numeric x | x (date/numeric), y (numeric), optional group |
| `area` | Volume or magnitude beneath a curve | x (date/numeric), y (numeric), optional group |
| `stacked_area` | Cumulative composition over time | x (date), y (numeric), group (required) |
| `stacked_bar` | Composition across discrete categories | x (string/bucketed date), y (numeric), group (required) |
| `bar` | Comparing unordered categories | x (string), y (numeric), optional group |
| `pie` | Part-of-whole across ≤ 10 categories | x (label), y (value) |
| `bubble` | Three-variable relationships | x, y, z (size), optional label or group |
| `scatter` | Two-numeric-axis relationships | x (numeric), y (numeric), optional group |
| `heatmap` | Intensity across two categorical axes | x (category), y (category), z (value or count) |
| `network` | Node-link relationships | x (source), y (target), optional z (edge weight) |
| `symbol_map` | Geographic point data on a world map | x (longitude), y (latitude), optional z (size), label, group |

### Faceting (small multiples)

Any `line`, `area`, or `scatter` chart with a `group_column` can be rendered as small multiples — one panel per group — instead of overlaid series:

| Prompt phrasing | `facet_direction` |
|---|---|
| "facet by", "small multiples", "one chart per", "panel per" | `columns` (side by side, wraps at 3) |
| "one per row", "stacked panels", "vertical facets" | `rows` (stacked, shared x-axis at bottom) |

Add "free scale" or "independent axes" to give each panel its own y-axis range; otherwise all panels share the same scale for direct comparison.

## Output

A single `.html` file with:
- Interactive hover tooltips on all chart types
- Visible gaps where data is missing (no silent drops)
- Axes extend to 1.2× the max value so data never crowds the edge
- **Edit panel** — click Edit (toggles to Save) to reveal in-browser controls:
  - **SVG Background** — color picker; axis/label/grid colors auto-flip dark/light based on background luminance
  - **Chart Size** — − / + buttons to resize
  - **Title / X Label / Y Label** — text inputs, update live
  - **Click any element** (bar, line, slice, bubble, node) to recolor it individually; in grouped charts, recoloring one element recolors the whole series
  - **Hot Color** (heatmap) — changes the high end of the sequential color scale live
  - **Node Color** (network) — global node color; individual nodes can still be clicked to override
  - **Spread** (network) — − / + adjusts force charge strength and restarts the simulation
  - **Land Color / Ocean Color** (symbol map) — change the country fill and ocean fill live
  - **Symbol Size** (symbol map) — − / + scales all symbols up or down
  - **Click any symbol** (symbol map, grouped) — recolors all symbols in that group
- **Copy SVG** — copies a static vector snapshot; works on `file://` via `execCommand` fallback
- **Download SVG** — saves an `.svg` file with all styles inlined; use Insert > Picture in PowerPoint for guaranteed vector quality
- `--svg-bg COLOR` — bake a custom SVG export background at generation time (default: `#1a1d27`)
- Network charts support drag-to-reposition nodes, scroll-to-zoom, and pan
- **Facet panels** (line/area/scatter) — one mini-chart per group; columns or rows layout; shared or independent y scales

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
| `--color` | `#6366f1` | Accent color — line/bar fill, bubble fill, node fill, heatmap hot end |
| `--palette` | — | Space-separated colors for grouped charts (one per group) |
| `--y-format` | `,.0f` | D3 format string for y-axis ticks |
| `--curve` | `monotoneX` | Line curve: `monotoneX`, `linear`, `step`, `natural`, `cardinal` |
| `--no-area` | off | Hide the gradient area fill (line chart) |
| `--svg-bg` | `#1a1d27` | SVG export background color |
| `--sort` | LLM decides | Override bar sort order: `asc`, `desc`, or `none` |

### Date bucketing

When the prompt mentions a time period, the LLM automatically buckets date x-values before aggregating:

```bash
python main.py data.csv "how has revenue changed per year?" --open
python main.py data.csv "show monthly active users per product" --open
python main.py data.csv "daily signups over Q1" --open
```

### Time period filtering

Narrow the x-axis to a specific range using natural language:

```bash
python main.py samples/sample.csv "show Acme revenue from March to September" --open
python main.py samples/stocks.csv "show AAPL price since 2010" --open
python main.py samples/nyc_restaurants.csv "inspections per year between 2022 and 2024" --open
```

The LLM converts the range to ISO date bounds (`x_min` / `x_max`) and the transformer filters rows before aggregating.

### Aggregation

The LLM picks the aggregation function from intent words in your prompt:

| Prompt phrasing | Aggregation |
|---|---|
| "total revenue", "cumulative sales" | `sum` (default for bar) |
| "average price", "typical order value" | `mean` |
| "number of orders", "how many" | `count` |
| "peak temperature", "highest score" | `max` |
| "lowest cost", "minimum price" | `min` |

Top-N filtering ranks groups by their aggregated total and keeps the N highest:

```bash
python main.py sales.csv "show the top 5 products by total revenue as a bar chart" --open
python main.py sales.csv "top 3 regions by average order value" --open
```

### Examples

**Line chart — single series:**
```bash
python main.py samples/sample.csv "show me Acme's revenue over time" \
  --title "Acme Revenue" --color "#10b981" --y-format '$,.0f' --open
```

**Line chart — multi-series:**
```bash
python main.py samples/sample.csv "compare revenue across all companies" \
  --title "Revenue by Company" --y-label "Revenue (USD)" --open
```

**Area chart — filled volume over time:**
```bash
python main.py samples/sample.csv "show revenue over time as an area chart for each company" --open
```

**Bar chart — total per category:**
```bash
python main.py samples/sample.csv "show total revenue per company" --color "#6366f1" --open
```

**Grouped bar chart:**
```bash
python main.py samples/sample.csv "compare monthly revenue for each company as grouped bars" --open
```

**Pie chart — part-of-whole:**
```bash
python main.py samples/sample.csv "show the revenue breakdown by company as a pie chart" --open
```

**Scatter chart — two numeric axes:**
```bash
python main.py samples/numeric_x.csv "show how income changes with age as a scatter plot" \
  --x-label "Age" --y-label "Income" --open
```

**Bubble chart — three variables:**
```bash
python main.py samples/iris.csv \
  "bubble chart of sepal length vs sepal width sized by petal length for each species" --open
```

**Bubble chart — individually labeled items:**
```bash
python main.py samples/starbucks_coffee.csv \
  "bubble chart of caffeine vs calories sized by sugar, label each drink" --open
```

**Heatmap — intensity across two categories:**
```bash
python main.py samples/diamonds.csv \
  "show a heatmap of average diamond price by cut and color" --open
```

**Network graph — unweighted connections:**
```bash
python main.py samples/airport_routes.csv \
  "show connections between airports as a network graph" --open
```

**Network graph — node size by total edge weight:**
```bash
python main.py samples/airport_routes.csv \
  "show a network graph of airport routes weighted by distance" --open
```

**Stacked bar chart — composition across months:**
```bash
python main.py samples/sample.csv \
  "show a stacked bar chart of monthly revenue for each company" --open
```

**Symbol map — world cities by population:**
```bash
python main.py samples/world_cities.csv \
  "plot world cities on a map, size each symbol by population and color by continent" --open
```

**Symbol map — labeled points:**
```bash
python main.py samples/world_cities.csv \
  "show a world map of cities with population as bubble size, label each city" --open
```

**Stacked bar chart — breakdown by category:**
```bash
python main.py samples/nyc_restaurants.csv \
  "stacked bar chart of inspection count by borough, broken down by critical flag" --open
```

**Facet — small multiples, columns layout:**
```bash
python main.py samples/sample.csv \
  "show revenue over time as a line chart with small multiples, one panel per company" --open
```

**Facet — small multiples, rows layout:**
```bash
python main.py samples/iris.csv \
  "facet the sepal length vs sepal width scatter plot in rows, one row per species" --open
```

**Facet — rows with independent y scales:**
```bash
python main.py samples/stocks.csv \
  "show stock price over time for each symbol in rows with a free y scale" --open
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
│   └── spec.py                    # AxisMapping, ChartConfig
├── pipeline/
│   ├── data_loader.py             # CSV ingestion and type detection
│   ├── llm_mapper.py              # Claude axis and chart type selection
│   ├── prompts.py                 # System prompts for LLM
│   ├── transformer.py             # Five transform modes (flat/grouped/labeled/heatmap/network)
│   ├── templater.py               # HTML rendering
│   └── templates/
│       ├── line_chart.html        # D3.js line chart (single + multi-series)
│       ├── area_chart.html        # D3.js area chart (per-group gradients)
│       ├── bar_chart.html         # D3.js bar chart (flat + grouped)
│       ├── pie_chart.html         # D3.js donut/pie chart with % labels
│       ├── scatter_chart.html     # D3.js scatter chart
│       ├── bubble_chart.html      # D3.js bubble chart (grouped or individually labeled)
│       ├── symbol_map_chart.html   # D3.js symbol map (Natural Earth projection + world-atlas CDN)
│       ├── stacked_area_chart.html # D3.js stacked area chart (composition over time)
│       ├── stacked_bar_chart.html  # D3.js stacked bar chart (composition across categories)
│       ├── heatmap_chart.html     # D3.js heatmap (sequential color scale + legend)
│       ├── network_chart.html     # D3.js force-directed network graph
│       └── facet_chart.html       # D3.js small multiples (line/area/scatter; columns or rows)
├── evals/
│   ├── cases.py                   # ~34 test cases covering all chart types and features
│   └── runner.py                  # CLI eval runner with keyword filtering and --fast mode
└── samples/
    ├── sample.csv                 # Multi-company revenue dataset (Date x-axis)
    ├── numeric_x.csv              # Age vs income dataset (Float x-axis)
    ├── stocks.csv                 # Stock prices by symbol over time
    ├── nyc_restaurants.csv        # NYC restaurant inspection records
    ├── iris.csv                   # Iris flower measurements by species
    ├── diamonds.csv               # Diamond prices by cut, color, and clarity
    ├── starbucks_coffee.csv       # Starbucks drink nutrition data
    ├── airport_routes.csv         # US airport route connections with distances
    └── world_cities.csv           # 55 major world cities with lat/lon, population, continent
```

## Eval suite

An LLM eval suite validates that the full pipeline (prompt → LLM mapping → transformer) produces the expected behaviour. Run it from `backend/`:

```bash
python -m evals.runner              # run all cases
python -m evals.runner heatmap      # run cases whose name contains 'heatmap'
python -m evals.runner --fast       # skip LLM calls; only validate transformer output
```

Each case specifies a CSV, a prompt, and assertions on both the `AxisMapping` the LLM returns and the transformer output shape/values. Covers: all eight chart types, aggregation, group/filter, top_n, sort_order, time_unit bucketing, x_min/x_max filtering, bubble z/label columns, heatmap cell counts, network node/link counts, and combined scenarios.

## Provider benchmarks

Run the eval suite against any provider with:

```bash
python -m evals.runner                                        # uses LLM_PROVIDER env var
python -m evals.runner --provider anthropic --model claude-haiku-4-5
python -m evals.runner --provider ollama --model gemma4:latest
```

Results across 34 cases covering all chart types, aggregation, date filtering, faceting, and top-N logic:

| Provider | Model | Passed | Failed | Pass rate | Avg latency | Total time |
|---|---|---|---|---|---|---|
| Anthropic | claude-haiku-4-5 | 34 | 0 | 100% | 1.6s | 53s |
| Ollama | qwen2.5-coder:7b | 28 | 6 | 82% | 3.3s | 108s |
| Ollama | gemma4:latest | 20 | 14 | 59% | 13.7s | 342s |

**Notes:**
- Gemma4 fails primarily on nuanced intent: date-range filtering (`x_min`/`x_max`), `top_n` extraction, and multi-column disambiguation
- Local models are faster per-token but load cold on each eval run; Haiku is faster end-to-end for short prompts
- Eval cases were written against Claude's behavior — a model that makes a different but valid chart choice will still fail

## What's next

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
- Intelligent peer selection — when a user focuses on one entity, the LLM picks structurally similar peers based on scale, sector, and growth trajectory
- Two-tier visual hierarchy — focus group gets distinct colors; peers render in a muted color at low opacity for context without clutter
- Pre-aggregation stage (`Summarizer`) that computes per-group stats before the LLM call, keeping token usage manageable on large datasets
