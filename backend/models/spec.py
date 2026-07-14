from pydantic import BaseModel


class PlotSpec(BaseModel):
    chart_type: str = "line"
    intent: str


class AxisMapping(BaseModel):
    x_column: str
    y_column: str


class ChartConfig(BaseModel):
    chart_type: str = "line"
    color: str = "#6366f1"
    show_area: bool = True
    curve: str = "monotoneX"     # any d3.curve* suffix: monotoneX, linear, step, natural
    y_format: str = ",.0f"       # d3 format string for y-axis ticks
    title: str = ""
    x_label: str = ""
    y_label: str = ""
