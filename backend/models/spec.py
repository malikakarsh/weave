from pydantic import BaseModel


class AxisMapping(BaseModel):
    chart_type: str = "line"
    x_column: str
    y_column: str
    group_column: str | None = None
    group_filter: list[str] | None = None  # specific group values to include; None means all
    aggregation: str = "sum"              # sum | mean | count | min | max
    top_n: int | None = None              # keep only top N groups by aggregated y; None means all
    sort_order: str = "asc"              # asc | desc | none — sort categories by y value (bar charts)
    time_unit: str | None = None         # year | month | day — truncate date x values before bucketing
    x_min: str | None = None             # inclusive lower bound on x (ISO date or number as string)
    x_max: str | None = None             # inclusive upper bound on x (ISO date or number as string)
    z_column: str | None = None          # bubble size column (numeric); only used for bubble chart type
    label_column: str | None = None      # column whose value labels each individual point (bubble name, etc.)
    facet_direction: str | None = None   # "rows" | "columns" — render as small multiples when set
    facet_free_y: bool = False           # True → each panel gets its own y scale; False → shared
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    color: str | None = None             # CSS color for single-series charts; null means use default palette
    category_colors: dict[str, str] | None = None  # per-category color overrides: {"CategoryName": "#hex"}
    palette: str | None = None            # named palette for grouped charts (e.g. 'dark', 'light', 'tableau10')
    background: str | None = None         # chart background color (CSS hex); null means use theme default


class ChartConfig(BaseModel):
    chart_type: str = "line"
    width: int = 836
    height: int = 420
    color: str = "#6366f1"
    show_area: bool = True
    curve: str = "monotoneX"     # any d3.curve* suffix: monotoneX, linear, step, natural
    y_format: str = ",.0f"       # d3 format string for y-axis ticks
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    z_label: str = ""                  # label for the z/size dimension (symbol map, bubble)
    x_column: str = ""
    y_column: str = ""
    palette: list[str] | None = None  # custom colors per group; falls back to D3 categorical scale
    category_colors: dict[str, str] | None = None  # per-category color overrides; merged on top of palette
    svg_bg: str = "#1a1d27"           # background rect injected into exported SVG
    background: str | None = None     # user-requested chart background (CSS hex); overrides theme when set
    facet_direction: str | None = None  # "rows" | "columns" — passed through from AxisMapping
    facet_free_y: bool = False          # True → each facet panel uses its own y scale
