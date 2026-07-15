from pydantic import BaseModel


class PlotSpec(BaseModel):
    chart_type: str = "line"
    intent: str


class AxisMapping(BaseModel):
    chart_type: str = "line"
    x_column: str
    y_column: str
    group_column: str | None = None
    group_filter: list[str] | None = None  # specific group values to include; None means all


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
    palette: list[str] | None = None  # custom colors per group; falls back to D3 categorical scale
    svg_bg: str = "#1a1d27"           # background rect injected into exported SVG
