# Weave

Turn a CSV file and a plain-English prompt into an interactive D3.js chart — no code required.

```bash
python main.py data.csv "show me revenue over time" --open
```

## Web UI

A Next.js frontend and FastAPI backend are included for browser-based chart generation.

**Start Postgres** (local dev, via Docker — data persists in a gitignored `./.pgdata/` bind mount):
```bash
docker compose up -d db
```

**Start the backend:**
```bash
cd backend
alembic upgrade head          # apply DB migrations (first run + after model changes)
uvicorn api.main:app --reload
```

**Start the frontend:**
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` — drop a CSV, describe your chart, and hit Generate.

Copy `backend/.env.example` → `backend/.env` and set your LLM key (`ANTHROPIC_API_KEY` / `GEMINI_API_KEY`) and `DATABASE_URL` (the default matches the docker-compose Postgres). Google sign-in gates chart generation (each generation/refine is metered per LLM call against a per-user daily limit): create an OAuth 2.0 Web client in Google Cloud Console with redirect URI `http://localhost:8000/auth/google/callback`, then set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `JWT_SECRET`, and `SESSION_SECRET`. Put your own email in `ADMIN_EMAILS` for unlimited admin access; `DAILY_REQUEST_LIMIT` (default 20) sets the cap for everyone else.

### Web UI features
- **Chart generation** — same pipeline as the CLI, rendered live in the browser
- **Iterative refinement** — after a chart is generated, keep chatting to refine it; the LLM sees the full conversation history and updates only the fields you ask about
- **Category disambiguation (human-in-the-loop)** — when you reference a category value ("color Good yellow", "show only America"), a deterministic `CategoryResolver` (not the LLM) matches your wording against the actual distinct values in the data. Exact and single-clean matches apply automatically; when a term is ambiguous ("America" → North/South America) or has no match, the chart asks you which value you meant with the **top-5 closest** options (ranked by similarity, above a floor) plus a "None of these" escape — then re-renders your pick with no extra LLM call. Templates match category colors exactly (so coloring `Good` no longer bleeds into `Very Good`)
- **Chart-type validation** — a deterministic `ChartValidator` (not the LLM) decides whether a chart type can be built from the data. Every generate/refine runs it against the dataset schema; impossible switches (e.g. "make it a bubble chart" with no numeric size column) are rejected with a clear "dimensions mismatch" message. The suggested alternative is computed, not hardcoded — the validator only offers chart types that actually validate against the current columns (so a rejected map won't suggest a scatter that would also fail, and won't suggest a radar for categorical axes just because the dataset has numeric columns elsewhere — a chart's columns must actually form its axes). A pipeline guard also restores any axis the LLM tried to swap to sneak past a requirement, so validation reflects the real columns. The schema + requirements are also fed to the refine LLM as advisory hints to reduce how often users hit an error
- **Conversation history** — a scrollable chat panel shows every user instruction and the mapping changes applied
- **Edit panel** — in-chart controls for title, axis labels, colors, and SVG background
- **Analyze chart** — sends the chart mapping + data sample to Claude for key insights
- **SVG export** — HD, Full HD, Social, Square presets plus custom dimensions
- **Light / dark mode** — toggle in the navbar; the chart template and map label colors adapt automatically; light mode uses a red accent (thread, buttons, WEAVE logo) while dark mode uses indigo
- **Auto-sizing iframe** — the chart container grows to fit its content with no empty space
- **Responsive landing page** — hero punchline scales from mobile through desktop; needle + thread SVG decoration; woven texture background
- **Readable map labels** — city/point labels use paint-order stroke halo so they're legible on both dark land and light ocean in any theme
- **Compact conversation history** — scrollable chat panel sized to show recent instructions without dominating the layout; scrollbar styled to match the active theme
- **Multi-chart dashboard** — one prompt generates multiple charts in parallel via SSE; each chart streams in as it finishes
- **Per-chart sessions** — every chart has its own isolated conversation history, mapping, and refine bar; changes in one chart never affect another
- **Add chart** — append new charts to a live dashboard at any time without clearing existing ones
- **Color refinement** — change any chart's overall color or a specific category's color via plain English ("change color to red", "make Not Applicable yellow"). "Make each cut a different color" colors a flat chart per category from a palette — a deterministic guard converts the degenerate grouping-by-the-x-axis the LLM tends to emit for this ask (skinny offset marks + a legend repeating the x labels) into the flat per-category coloring that was meant
- **Palette refinement** — switch a chart's color scheme by name ("use a dark palette", "change the palette to tableau colors", "pastel palette"); the `vibrant`/`dark`/`light`/`muted` ramps share a golden-angle HCL hue scale (perceptually uniform, only chroma/lightness change) and `tableau10`/`category10`/`set2`/`dark2`/`pastel` are the familiar categorical schemes. Grouped charts use the full palette; single-series (unicolor) charts adopt the palette's first shade, so "dark palette" / "light palette" work on them too (an explicit "change color to …" still takes precedence)
- **Mark-size refinement** — resize a chart's marks by plain English ("make the bars wider", "thinner bars", "thicker lines", "bigger points", "smaller bubbles"); a single `mark_scale` multiplier drives bar width, line/area stroke thickness, and scatter/bubble/facet point radius, and relative asks ("a bit bigger", "much smaller") scale the current size (clamped to 0.2–4×)
- **Legend relabeling** — rename the legend/series labels in plain English ("label 0 as death and 1 as survived", "rename the legend to Yes/No"); a `group_labels` map ({rawValue: displayLabel}) renames only the legend + tooltip text, without filtering, recoloring, or re-aggregating. Applied across every grouped chart type (bar, line, area, stacked bar/area, scatter, bubble, box, violin, histogram, radar). Set back to null to revert to the raw values
- **Interactive filter sliders** — add live filter controls under a chart in plain English ("add a year slider", "add a minimum wins filter", "filter sepal width between a min and a max"). Filtering is **entirely client-side with no server round-trip and no raw rows shipped**: a `scrub` control steps through a discrete column's values (the server pre-computes one fully-aggregated slice per value; the slider just swaps which pre-built slice is shown, so it scales regardless of raw row count), and `min`/`max` controls are thresholds applied in the browser. Wired for **all 15 chart types** (bar, pie, scatter, line, area, stacked area, stacked bar, histogram, box plot, violin, radar, heatmap, network, symbol map, facet). A shared runtime (`_controls_runtime.html`, injected once by the templater) provides the slider UI + filter logic; each chart exposes a re-callable draw so scrubbing/thresholding re-render instantly and compose with the edit panel.
  - **Stable frame** — axes, legend, and series colors are fixed from the **union of all slices** (for stacked charts the y-max is the largest stack *total*), so only the marks re-render as you scrub. Network keeps a single persistent force simulation and matches surviving nodes by id so the layout doesn't scatter; facet's panel grid is the union of groups so it never reflows.
  - **min / max / range** — a `min` slider hides marks below a value, a `max` slider hides marks above; a min + max on the same column is a range pair. Each threshold carries a **field** (`x`/`y`/`z`/measure) so it filters the value of the column it *names* — "minimum sepal length" filters the x-axis, "minimum wins" filters the aggregated measure — and its bound follows suit (raw coordinate vs aggregated). Radar is scrub-only (a threshold would corrupt polygon/axis alignment).
  - **dropdown picker** — "add a year dropdown" renders a `<select>` instead of a slider; same one-slice-per-value slicing as scrub, for unordered or many-valued categoricals where a slider is awkward. Composes with a scrub as a second dimension.
  - **network-aware filtering** — on a node-link graph the same plain-English controls mean graph-specific things, disambiguated deterministically: a **"minimum connections" filter** thresholds node *degree* (a virtual `connections` column so it stays referenceable across refinements — "remove the connections filter" targets the right one), while a **value filter** ("minimum constructor points") thresholds the node's aggregated size and adopts that column as the graph weight if the graph was unweighted. Edge semantics differ by kind: a degree filter keeps hubs plus their neighbourhoods (ego-network — a bipartite graph would otherwise lose every edge), and a value filter applies only to the **side that owns the measure** so the opposite side stays as context (a low-points constructor drops, its races remain; a race whose constructors are all filtered out drops with them).
  - **Date bucketing + composable scrubs** — a scrub on a raw date column steps by period (auto-year, or `time_unit` for month/day), never one timestamp at a time. Up to **two scrub sliders compose** — "add a year and a month slider" yields separate Year and Month sliders over one date column, slices pre-computed per (year, month) combination (capped, defaulting to the newest combination with data).
  - **Time-axis windowing** — a scrub on a continuous/temporal **x-axis** (line/area/facet) *windows* it: each slice rescales the x to its period, so "month slider" shows one month across the full panel. A scrub on a categorical x, or one that can't be applied, is dropped so the chart keeps its full axis.
  - A bare "min/max `<column>` filter" is disambiguated from a hard cutoff both in the prompt and by a deterministic guard that promotes a mis-emitted `filters` threshold into a control slider (a wrong guessed cutoff can't empty the chart)
- **Adaptive y-axis format** — the y-axis honours the configured tick format, but falls back to decimal precision when integer formatting would collapse ticks into duplicate labels (e.g. sepal width 2.5/3.0/3.5 no longer all read "3")
- **Refinement error messages** — a refinement that can't be applied surfaces a clear reason instead of a silently unchanged chart: a referenced column that isn't in the data ("There's no 'clarity' column…, available columns: …"), a no-op instruction the model couldn't map to any change, and a filter/column combination that produces no rows all show in a red banner under the chart while keeping the existing chart on screen
- **Voice input** — a mic button on every prompt, add-chart, and refine bar uses the browser-native `SpeechRecognition` API; toggle recording with the **⌥/Alt+Shift+V** shortcut (targets the field you're working in — prompt on the landing page, the current chart's refine bar on the dashboard) and press **Enter** to submit the transcript
- **Google sign-in** — login via Google OAuth (with `prompt=select_account`, so the account chooser always appears). The FastAPI backend owns identity: Google only authenticates, then the backend mints its **own JWT** in an httpOnly cookie (`api/auth.py`) and upserts the user in Postgres — it's the single source of truth for who the user is. Chart generation requires sign-in; the navbar shows "Sign in with Google" or the user's avatar + a logout menu
- **Consistent theme** — the light/dark choice is persisted (`useTheme`, localStorage) and shared across the landing, docs, and admin pages
- **Roles + daily limits** — an admin role (`ADMIN_EMAILS`) with unlimited access; everyone else gets a per-user daily quota **metered per LLM call** (`DAILY_REQUEST_LIMIT`, default 20). A navbar pill shows requests remaining (amber when low, red at 0); a multi-chart prompt is capped to the remaining quota, and hitting the limit returns a clear message
- **Saved threads** — each CSV upload starts a **thread** (Claude-style): its charts + refine histories auto-save to Postgres, scoped to your account. A sidebar lists past threads; click one to restore the CSV and all its charts. Rename any thread inline (pencil button or double-click the title; Enter saves, Escape cancels — applied optimistically via `PATCH /threads/{id}`) and delete it from the same row. They persist across logout, browser close, and other devices; the sidebar scrollbar matches the active theme
- **Admin dashboard** — admins get an `/admin` view (linked from the profile menu) listing every user with their page-open count, today's + total LLM calls, last-seen, and join date, plus headline totals. Backed by `api/admin.py` and a `require_admin` dependency that re-checks the role **against the database** (not the JWT claim), so access can be revoked instantly and a stale/forged-claim token can't get in — non-admins get 403, unauthenticated 401. Page opens are tracked via `POST /auth/visit` on load. Admins can **edit any user's daily limit inline** (`PATCH /admin/users/{id}`) — a per-user `daily_limit` override that the quota checks read from the DB, so it takes effect instantly; leaving it blank resets to the global `DAILY_REQUEST_LIMIT`
- **Live model-performance metrics** — a real-time panel on `/admin` comparing every provider/model actually used on **latency (avg + p95), call volume, error rate, tokens (total in/out), average tokens per call (in/out), and estimated cost**. Capture is deterministic and central: `get_provider()` wraps the provider in a `MeteredProvider` (`pipeline/providers/metrics.py`) that times every `complete()` call and buffers a record (provider, model, latency, ok, token usage) in-process; a background flusher persists the buffer to the `llm_calls` table every ~2s (so nothing is lost when no one's watching). The panel streams over **SSE** (`GET /admin/metrics/stream`, `require_admin`): the server flushes + aggregates every 2s (`percentile_cont` for p95, grouped by model) and pushes it to the browser's `EventSource`, which updates the table live with a pulsing indicator. Cost is derived from tokens × a `MODEL_PRICING` map at query time (so prices can change with no backfill; unknown models show "—")
- **Prompt caching** — the large, static system prompt (~3k tokens) is identical on every call, so it's cached server-side instead of re-uploaded each time. **Anthropic** marks it with a `cache_control` ephemeral block (single + batch calls); **Gemini** uploads it once as explicit context cache, keyed by `(model, prompt-hash)` in a process-wide registry and reused within a 10-minute TTL. Both degrade gracefully — if the prompt is below the model's minimum cacheable size (or the SDK/cache is unavailable), generation falls back to the uncached path with no error. Metered "tokens in" counts cache reads/writes so the numbers stay comparable
- **Rounded chart container** — the chart iframe has rounded corners and a subtle shadow that adapts to light/dark mode
- **Numeric x-axis fidelity** — for a numeric x-axis (line/area/stacked-area/scatter/bubble/facet), the domain fits the data (`[min, max]`, or a range-based pad for marker charts) instead of stretching to `1.2×` the max — so a **year** axis no longer runs to `2400` and crushes the data into a sliver. Integer x-values (years, ages) get integer tick values with no thousands separator, so a year reads `2021`, never `2,021.5`
- **Tooltip behavior** — hover tooltips (line/area/scatter) stay fully inside the viewport: they prefer the side of the cursor with room, flip when they'd overflow, and clamp on both axes so a tall multi-series box never spills past the chart edge; they follow the cursor's height rather than pinning to one series' value, so the box never lands on top of the pointer. Multi-series snapping references the **union of every series' x values**, so the tooltip header year and each row's value always line up — even when one series is missing a year the others have
- **Upload-gated prompt bar** — the prompt input, mic button, and generate button stay disabled until a CSV is uploaded, with a "Upload a CSV to get started…" hint
- **In-app docs** — a `/docs` page (linked from the navbar) documenting how Weave works: getting started, the refinement commands ("flags") with examples, the full chart-type catalog, faceting, interactive controls (sliders/dropdowns/threshold + network filters), voice, accounts/threads/limits, and export. Centered article with a fixed left-rail table of contents on desktop and a slide-in section drawer on mobile; matches the app's sun/moon theme toggle, red/indigo accent, and viewport-pinned radial-mesh background
- **Playground** — pick a sample dataset from the landing page (Stocks, Revenue, World Cities, Diamonds, NYC Restaurants, Iris) to see auto-generated dashboards and experiment with refinements; resets when you upload your own CSV
- **Multi-CSV joins** — drop several related CSVs at once and Weave combines them into one wide table before charting. A deterministic join engine (`pipeline/multi_csv.py`, in-memory SQLite) detects foreign keys by **value overlap** gated on **key-name compatibility** — stem matching so `raceId`→`raceId` and `orders.user_id`→`users.id` join, while cross-entity collisions (`statusId`↔`raceId`), two bare `id` primary keys, and same-named measures (`points`↔`points`) never do. It builds a maximum-confidence spanning tree over the tables and supports **composite-key joins** (e.g. `results ⋈ driver_standings ON raceId AND driverId`) so many-to-one detail tables attach 1:1. Overlap is measured against the **full referenced column**, not two independently-capped samples, so a foreign key that points at the tail of a large dimension table (e.g. `sprint_results.raceId` → the most recent `races`) is still detected instead of falsely reading zero overlap. A **fan-out guard** leaves any table that would multiply rows unjoined rather than silently corrupting counts. The Combine dialog shows every detected join (composite ones badged), lets you choose the base table and toggle joins, and reports which tables couldn't be linked; join plans validate and execute **order-independently** (steps grown to a fixpoint from the base), so any connected plan works regardless of step order or which base you pick. No LLM call — it's schema-driven and deterministic
- **Show columns** — type "show columns" / "show schema" (deterministically detected, so it never builds a chart) to open a modal listing every column with its inferred type, **min/max range** (numeric range, date span, or A→Z for text), and sample values — handy for verifying what actually landed in a joined table
- **Numeric range filters** — filter any numeric column by threshold in plain English ("wins ≥ 3", "between 18 and 65", "at most 100"), not just exact values. Multiple filters on the same column combine as OR and across columns as AND, and re-filtering a dimension replaces rather than stacks, so "for 2016" after "for 2013" can't collapse to an empty result

## How it works

Weave runs a four-stage pipeline:

```
DataLoader → LLMMapper → Transformer → Templater
```

1. **DataLoader** — reads the CSV, auto-detects delimiter, skips title/banner and blank preamble rows to find the real header, drops empty trailing/interior columns, infers column types (Date, Float, String), and validates that the dataset has at least one numeric column. Numeric detection is format-tolerant — `$6.52`, `-1,200.00`, `(350.00)` accounting negatives, `85%`, and `-` placeholder gaps are all recognised. Date detection covers ISO, day/month/year and month/day/year with 4- or 2-digit years (`09/02/25`), dashed variants, and abbreviated-month forms (`Aug 19 2004`).

2. **LLMMapper** — sends the schema and your prompt to Claude, which decides the chart type (line, area, bar, histogram, box_plot, violin, radar, pie, bubble, scatter, heatmap, network), picks the x/y/group/z/label columns, chooses an aggregation function (sum/mean/count/min/max) based on intent words in the prompt, optionally limits to the top N groups by aggregated value, sets a time unit (year/month/day) when the prompt asks for period-level bucketing of date columns, and applies x_min/x_max bounds for time period filtering.

3. **Transformer** — routes to one of nine transform modes based on the mapping:
   - **flat** — aggregates rows by x into `{x, y}` pairs (single series)
   - **grouped** — aggregates by (group, x) into `{group, values}` objects (multi-series)
   - **labeled** — one point per row with no aggregation; `{x, y, z, label}` (bubble with named items)
   - **heatmap** — categorical axes → one `{x, y, z}` cell per value pair (matrix); numeric axes → binned `{x0, x1, y0, y1, z}` density grid (2D histogram)
   - **network** — aggregates edges by (source, target) into `{nodes, links}`; an optional numeric measure sizes nodes and weights edges with **deterministic grain-aware aggregation** — a value repeated or accumulated across rows (a season total, a cumulative running total) is collapsed to one representative instead of being summed per row, and a measure that's an attribute of a node itself is counted once rather than summed across its neighbours, so neither is double-counted. Nodes are colored by which side (source vs target) they belong to, with a legend
   - **box** — computes a five-number summary + outliers per category (no aggregation to a single value)
   - **violin** — computes a kernel-density curve (KDE) + summary per category for distribution-shape plots
   - **histogram** — bins one numeric column (Freedman-Diaconis) and counts rows per bin
   - **radar** — melts several metric columns (or long axis/value data) into per-entity axis values

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
| `histogram` | Frequency distribution of one numeric column (auto-binned) | x (numeric), optional group |
| `box_plot` | Distribution (median, quartiles, whiskers, outliers) per category | x (category), y (numeric), optional group |
| `violin` | Distribution shape (kernel-density curve + inner box) per category | x (category), y (numeric), optional group |
| `radar` | Compare several numeric metrics across entities on radial axes | metric_columns (numeric), group (entity); or x (metric)/y/group |
| `pie` | Part-of-whole across ≤ 10 categories | x (label), y (value) |
| `bubble` | Three-variable relationships | x, y, z (size), optional label or group |
| `scatter` | Two-numeric-axis relationships | x (numeric), y (numeric), optional group |
| `heatmap` | Matrix (two categorical axes) or density / 2D histogram (two numeric axes, auto-binned) | x, y (both category, or both numeric), z (value or count) |
| `network` | Node-link relationships | x (source), y (target), optional z (edge weight) |
| `symbol_map` | Geographic point data on a world map | x (longitude), y (latitude), optional z (size), label, group |

### Planned chart types

These are not yet supported. Weave currently falls back to the closest available alternative (noted below) when these are requested.

| Type | Best for | Planned fallback today |
|---|---|---|
| `candlestick` | OHLC financial price data over time | line |
| `waterfall` | Cumulative change — running total with positive/negative bars | bar |
| `funnel` | Step-by-step conversion / drop-off rates | bar (sorted desc) |
| `treemap` | Hierarchical part-of-whole with nested rectangles | pie / bar |
| `sankey` | Flow of values between stages or nodes | network |
| `calendar_heatmap` | Daily value intensity across a full year (like GitHub activity) | heatmap |
| `bump` | Rank over time — how entities rise and fall in position (y = rank, x = time, one line per entity) | line |
| `streamgraph` | Flowing stacked area centered on a baseline — shows volume and composition over time with an organic, river-like shape | stacked_area |

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

**Cumulative / standings columns aggregate as `max`, not `sum`.** A running total or point-in-time snapshot (a name-token like `standings`, `cumulative`, `running`, `career`, `ytd`) repeats its accumulated figure on every underlying row, so summing it double-counts — e.g. summing `constructor_standings_wins` across every result row wildly inflates the total. The mapper detects these deterministically (token-matched, so `outstanding` ≠ `standing`) and flips a plain `sum` to `max` (the terminal value) on both generation and refine; an explicit `mean`/`count`/`min`/`max` and genuinely additive facts (`revenue`, race `wins`, `points`) are left untouched.

Top-N filtering ranks groups by their aggregated total and keeps the N highest:

```bash
python main.py sales.csv "show the top 5 products by total revenue as a bar chart" --open
python main.py sales.csv "top 3 regions by average order value" --open
```

**Dimension-targeted limiting & filtering** — in a grouped chart there are two categorical dimensions (x-axis and grouping), so "top three colors" is ambiguous if limits only ever apply to one of them. The LLM can instead emit **column-referenced** specs that name the dimension explicitly:

- `limit` — `{"column": "color", "n": 3}` keeps the top 3 x-axis colors; `{"column": "cut", "n": 2}` keeps the top 2 groups. Ranked by the chart's aggregation.
- `filters` — `[{"column": "cut", "values": ["Premium", "Fair"]}]` keeps only those values of any named column.

Both are applied as row-level pre-filters before aggregation, so they work on the x-axis, the grouping, or any other column without the model having to guess which dimension you meant. (The legacy `top_n`/`group_filter` still work for plain single-dimension requests.)

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

## Deployment (Docker + Cloudflare Tunnel)

The whole stack — Next.js frontend, FastAPI backend, Postgres — runs from one `docker-compose.yml`, and a `cloudflared` container exposes it publicly over HTTPS with **no port-forwarding**. This is how you host it on a spare machine and share a link.

**Architecture:** two subdomains of one domain — `https://<APP_HOST>` → frontend, `https://<API_HOST>` → backend. Because they're the same registrable domain (same-site), the existing `SameSite=Lax` auth cookie flows and Google OAuth works with **no code changes** — the backend just runs uvicorn with `--proxy-headers` so it sees the real public host. Cloudflare's tunnel ingress routes both hostnames to the containers, so no reverse proxy is needed.

**One-time setup**
1. **Cloudflare Zero Trust → Networks → Tunnels**: create a tunnel, copy its token. Add two public hostnames — `<APP_HOST> → http://frontend:3000` and `<API_HOST> → http://backend:8000`.
2. **Google Cloud Console → OAuth client**: add redirect URI `https://<API_HOST>/auth/google/callback` and JS origin `https://<APP_HOST>`. If the consent screen is in "Testing", add each tester's email as a test user.

**Deploy**
```bash
cp .env.production.example .env    # fill in hosts, secrets, tunnel token, LLM + Google keys
docker compose up -d --build       # db → migrate → backend → frontend → cloudflared
docker compose logs -f backend     # watch "Running database migrations" then "Starting API"
```
Share `https://<APP_HOST>`. `alembic upgrade head` runs automatically on backend start; Postgres data persists in the gitignored `./.pgdata` bind mount.

**Notes**
- `NEXT_PUBLIC_API_URL` is inlined into the frontend bundle at **build time**, so changing `<API_HOST>` means `docker compose build frontend` again.
- Set `COOKIE_SECURE=1` (the template does) — required for cookies over HTTPS.
- If you ever split frontend/backend onto *different* domains (not subdomains), switch `samesite` to `"none"` in `_set_session_cookie` (`backend/api/auth.py`), since `Secure` is already set.

## Project structure

```
backend/
├── main.py                        # CLI entry point
├── requirements.txt               # Python dependencies
├── .env.example                   # Template for LLM keys + Google OAuth / JWT config
├── api/
│   ├── main.py                    # FastAPI app: chart/dashboard/refine SSE endpoints, CORS, session
│   ├── auth.py                    # Google OAuth (Authlib) + httpOnly-cookie JWT session; roles; user upsert
│   ├── usage.py                   # Per-user daily rate limiting (metered per LLM call; admins exempt)
│   ├── threads.py                 # User-scoped thread CRUD + chart persistence
│   ├── admin.py                   # Admin-only user/usage dashboard endpoints
│   ├── joins.py                   # Multi-CSV join detect/execute endpoints (deterministic, no LLM)
│   ├── db.py                      # Async SQLAlchemy engine, session factory, get_db dependency
│   └── db_models.py               # ORM models: User, Thread, Chart, DailyUsage
├── alembic/                       # DB migrations (async env; versions/ holds each revision)
├── alembic.ini                    # Alembic config (DB URL injected from DATABASE_URL)
├── models/
│   ├── schema.py                  # ColumnType, ColumnInfo, Schema
│   └── spec.py                    # AxisMapping, ChartConfig
├── pipeline/
│   ├── data_loader.py             # CSV ingestion, header/preamble detection, type detection
│   ├── numeric.py                 # Tolerant numeric parsing ($, commas, %, accounting negatives)
│   ├── csv_validator.py           # Upload safety checks (size, encoding, formula-injection guard)
│   ├── multi_csv.py               # Multi-CSV join engine (SQLite; value-overlap + key-name FK detection, composite keys, fan-out guard)
│   ├── llm_mapper.py              # Claude axis and chart type selection
│   ├── prompts.py                 # System prompts for LLM
│   ├── palettes.py                # Named color palettes (HCL ramps + categorical schemes)
│   ├── chart_requirements.py      # Per-chart-type dimension checks (validate + suggest alternative)
│   ├── category_resolver.py       # Deterministic category-value resolution + ambiguity clarification
│   ├── transformer.py             # Transform modes (flat/grouped/labeled/heatmap/network/box/violin/histogram/radar) + numeric filters + grain-aware measure collapse
│   ├── templater.py               # HTML rendering
│   └── templates/
│       ├── line_chart.html        # D3.js line chart (single + multi-series)
│       ├── area_chart.html        # D3.js area chart (per-group gradients)
│       ├── bar_chart.html         # D3.js bar chart (flat + grouped)
│       ├── box_plot_chart.html    # D3.js box plot (quartiles, whiskers, outliers; flat + grouped)
│       ├── violin_chart.html      # D3.js violin plot (KDE density + inner box; flat + grouped)
│       ├── histogram_chart.html   # D3.js histogram (auto-binned numeric column; flat + grouped overlay)
│       ├── radar_chart.html       # D3.js radar/spider (per-axis normalized polygons; wide or long data)
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
│   ├── cases.py                   # 51 test cases covering all chart types, refine, and fallbacks
│   └── runner.py                  # CLI eval runner with keyword filtering and --fast mode
├── tests/
│   ├── conftest.py                # shared fixtures (tmp_csv, flat_mapping)
│   ├── test_data_loader.py        # DataLoader unit tests (type detection, header detection, load, validate)
│   ├── test_numeric.py            # Tolerant numeric parser (currency, separators, negatives, placeholders)
│   ├── test_csv_validator.py      # Formula-injection guard (real formulas vs formatted numbers)
│   ├── test_transformer.py        # Transformer unit tests (all transform modes, sort, bucketing, range)
│   ├── test_llm_mapper.py         # LLMMapper unit tests (deterministic helpers + mocked provider)
│   ├── test_chart_requirements.py # ChartValidator rules (valid + mismatch cases)
│   ├── test_pipeline_guard.py     # Axis-preservation guard on chart-type changes
│   └── test_category_resolver.py  # Category resolution tiers (exact/unique/ambiguous/none)
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
python -m evals.runner              # run all cases (sequential — one call per case, with latency)
python -m evals.runner heatmap      # run cases whose name contains 'heatmap'
python -m evals.runner --batch      # submit all cases as one batch (cheaper, no per-case latency)
python -m evals.runner --fast       # skip LLM calls; only validate transformer output
```

**Execution modes** — by default the runner calls the model once per case sequentially and reports per-case and aggregate latency (useful for benchmarking). Pass `--batch` to build one request per case and submit them all at once: on Anthropic this uses the [Message Batches API](https://docs.anthropic.com/en/docs/build-with-claude/batch-processing) (one async job, ~50% cheaper but higher wall-clock latency); other providers fan the requests out concurrently. Only the eval runner batches — the app pipeline always uses single requests. `LLMMapper` exposes `build_map_request`/`parse_map_response` (and the refine equivalents) so the runner can build every prompt up front, submit the batch, then parse each response.

Each case specifies a CSV, a prompt, and assertions on both the `AxisMapping` the LLM returns and the transformer output shape/values. 51 cases covering:

| Category | What's tested |
|---|---|
| Chart type selection | line, area, stacked_area, stacked_bar, bar, histogram, box_plot, violin, radar, pie, bubble, scatter, heatmap, network, symbol_map, facet |
| Aggregation | sum, mean, count — triggered by intent words in the prompt |
| Group / filter | multi-series grouping, single and multi-value group_filter |
| Top N | top_n ranking by aggregated y value |
| Dimension limit | column-referenced `limit` keeps the top N of a named dimension (e.g. top 3 colors in a color × cut grouped chart) |
| Sort order | asc, desc, none — including "highest first" phrasing |
| Date bucketing | time_unit year / month / day |
| Date range filtering | x_min / x_max bounds |
| Box plot fallback | box plot / violin / histogram → bar + mean |
| Refine: sort | "sort descending" / "sort ascending" changes only sort_order |
| Refine: color | overall color change and per-category color override |
| Refine: mark size | 'thinner bars' sets mark_scale below 1.0 |
| Refine: background | chart background change via natural language ("change the background to white") |
| Refine: chart type | switching chart type mid-conversation |
| Refine: top N | reducing to top N via refine instruction |
| Refine: group filter | narrowing to specific series via refine |
| Refine: field stability | fields not mentioned in instruction stay unchanged |

In `--fast` mode the LLM is skipped: refine cases merge `expect_mapping` onto `refine_from` to simulate the refined result, and transformer assertions still run. Cases that only assert LLM behavior (partial `expect_mapping` without required columns) are skipped in fast mode — they require a real LLM call.

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

**API + UI** ✓
- ~~FastAPI backend — `POST /chart`, `GET /health`~~
- ~~Frontend — file upload + prompt input + rendered chart in browser~~
- ~~`POST /refine` — iterative chart refinement with conversation history~~
- ~~Universal prompt bar — single input drives both generation and refinement~~
- ~~Responsive hero landing page~~
- ~~Multi-chart dashboard — `POST /dashboard` SSE endpoint; LLM decomposes one prompt into N focused sub-prompts, runs N pipelines in parallel via `asyncio.as_completed`, streams each chart to the browser as it finishes~~
- ~~Per-chart session state — each chart has its own isolated conversation history, mapping, and refine bar; refinements in one chart never affect another~~
- ~~"Add chart" button — append new charts to the dashboard at any time without clearing existing ones~~
- ~~CSV validation — size limit (50 MB, generous enough for combined multi-CSV joins), encoding check, null-byte detection, parse verification, formula injection guard (formatted numbers, `-`/`+`/`.` placeholders, and signed-with-units values like `+1 Lap` / `-5.478` are not mistaken for formulas)~~
- ~~Color refinement — `color` and `category_colors` fields in `AxisMapping`; overall color and per-category overrides via natural language~~
- ~~Playground — sample dataset picker on landing page; backend serves CSVs via `GET /playground/csv/{id}`; reuses dashboard SSE pipeline; resets on own CSV upload~~
- ~~Navbar cursor fix — pointer cursor on theme toggle and "← New" button~~
- ~~Google OAuth login — FastAPI-owned flow (`api/auth.py`, Authlib): Google authenticates, backend mints its own httpOnly-cookie JWT; `/auth/login/google`, `/auth/google/callback`, `/auth/me`, `/auth/logout` + a `get_current_user` dependency; frontend `useAuth` hook + navbar sign-in/avatar. Stateless (JWT-carried identity) until the user table lands with persistence~~
- Deployed with a live URL (Digital Ocean)

**Test suite** ✓
- ~~pytest unit tests — DataLoader (type detection, CSV loading, validation), Transformer (all six transform modes, sort, date bucketing, range filtering), LLMMapper (fence stripping, schema description, validate, map/refine with mocked provider)~~

**Streaming** ✓
- ~~SSE progress stream — `POST /chart/stream` and `POST /refine/stream` emit `loading → mapping → transforming → rendering → done` stage events; dashboard SSE emits per-chart `progress` events; frontend shows a 4-step progress bar and stage label in each pending card~~

**Multi-CSV joins** ✓
Uploading multiple CSVs (e.g. an F1 dataset split across races, results, drivers, constructors, standings) and visualising across them, via a join stage before the existing pipeline.

Architecture (shipped, fully deterministic — no LLM in the join path):
- ~~Load all CSVs into an in-memory SQLite database~~
- ~~Auto-detect join candidates using **value-overlap sampling** gated by **key-name compatibility** (stem matching) — so `results.driverId`→`drivers.driverId` joins, but cross-entity collisions (`statusId`↔`raceId`), two bare `id` PKs, and same-named measures (`points`↔`points`) are rejected even when their integer ranges overlap~~
- ~~**Composite-key detection** — tables sharing 2+ key columns whose combination is unique on one side join on all of them (`results ⋈ driver_standings ON raceId AND driverId`), a 1:1 lookup~~
- ~~**Fan-out guard** — a table is only auto-joined when its own join key is unique on its side; a many-to-one detail table (season standings keyed on `raceId` alone) is left unjoined rather than exploding the fact grain~~
- ~~Maximum-confidence spanning tree (Prim's) picks the base/fact table and connects the rest; the Combine dialog lets the user confirm the base table, toggle joins (composite ones badged), and see which tables couldn't be linked~~
- ~~Executed result is a flat table that drops into the existing LLMMapper → Transformer → Templater pipeline unchanged~~

**Deterministic grain-aware aggregation** ✓
- ~~When a chart aggregates a measure, a coarse-grained column repeated across fine-grained rows (the BI "fan trap") is collapsed to one representative per group before aggregating — constant → the value, cumulative/monotonic → the terminal value, otherwise the requested aggregation. Applied to the network's node/edge sizing so a repeated season total or a cumulative running total (e.g. `wins`) is never multiplied by the number of underlying rows. Domain-agnostic, works on directly-uploaded denormalised CSVs too~~

**Canvas / dashboard view**
- Multiple charts on one page, each independently generated from its own CSV + prompt
- "Add chart" button — pick a CSV, write a prompt, generate a new chart into the canvas
- Each chart has its own chat-style refinement thread
- Provider / model switcher per chart (Claude vs Ollama, haiku vs sonnet)

**Chart sharing**
- Store generated HTML server-side (UUID key → blob storage or DB)
- Serve at `GET /chart/{id}` — returns self-contained HTML
- Give users an `<iframe src="https://weave.app/chart/{id}">` embed snippet; all interactivity (tooltips, edit panel, export) works client-side with no server dependency after load

**Speech to text** ✓
- ~~Microphone button on every prompt, add-chart, and refine bar — click to start/stop recording~~
- ~~Browser-native `webkitSpeechRecognition` / `SpeechRecognition` API (zero backend changes, works in Chrome/Edge out of the box); transcript drops into the existing input so the rest of the flow is unchanged~~
- ~~**⌥/Alt+Shift+V** keyboard shortcut toggles recording for the field in context (prompt on the landing page, the current chart's refine bar on the dashboard); **Enter** submits the transcript~~

**Session persistence**
- ~~Database foundation — Postgres (local: docker-compose, bind-mounted to `./.pgdata`), async SQLAlchemy 2.0 + asyncpg, Alembic migrations; `User` / `Thread` / `Chart` / `DailyUsage` models (`api/db_models.py`); the user is upserted from their Google profile on every login~~
- ~~Roles + rate limiting — `User.role` (admin via `ADMIN_EMAILS`); per-user daily limit (`DAILY_REQUEST_LIMIT`, default 20) **metered per LLM call** in a `daily_usage` table (`api/usage.py`), admins exempt. Every LLM endpoint requires login and charges quota; a multi-chart dashboard is capped to the remaining quota and returns `429` when exhausted~~
- ~~Thread persistence (backend) — a **thread** is one CSV-upload workspace (title + CSV + its charts, each keeping its refine history). User-scoped CRUD in `api/threads.py` (`POST/GET/GET{id}/PUT charts/PATCH/DELETE /threads`); ownership enforced (404 on someone else's thread)~~
- ~~Frontend — thread sidebar (list past threads, new thread on CSV upload, click to restore full state incl. refine history), navbar usage indicator (`remaining/limit`, admin badge) that refreshes after each call, and login-gated generation. Charts auto-save (debounced) to the current thread; `app/threads.ts` is the API client, `app/useAuth.ts` exposes role + usage~~
- ~~Charts persist server-side per user (Postgres), so they survive logout, browser close, and other devices — restored from the sidebar on next sign-in~~
- ~~Return to the last page you were on across reloads — the CSV, charts, and current thread are restored from IndexedDB (not an auto-jump to the newest thread), so you land back exactly where you left off (or on the landing page if that's where you were)~~

**Data storytelling**
- Intelligent peer selection — when a user focuses on one entity, the LLM picks structurally similar peers based on scale, sector, and growth trajectory
- Two-tier visual hierarchy — focus group gets distinct colors; peers render in a muted color at low opacity for context without clutter
- Pre-aggregation stage (`Summarizer`) that computes per-group stats before the LLM call, keeping token usage manageable on large datasets
