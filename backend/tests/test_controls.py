"""Interactive-control payload: the server pre-computes per-value slices for a
scrub slider and threshold bounds for a min slider, all client-side-ready."""

from models.spec import AxisMapping, ControlSpec
from pipeline.transformer import Transformer


def _f1_rows():
    rows = []
    for year in ["1965", "1966", "1967"]:
        for team, wins in [("Lotus", 2), ("Brabham", 3), ("Cooper", 0)]:
            for _ in range(wins or 1):
                rows.append({"year": year, "constructor": team, "wins": str(wins)})
    return rows


def _payload(controls):
    m = AxisMapping(chart_type="bar", x_column="constructor", y_column="wins",
                    aggregation="sum", controls=controls)
    return Transformer().build_control_payload(_f1_rows(), m)


class TestControlPayload:
    def test_none_when_no_controls(self):
        m = AxisMapping(chart_type="bar", x_column="constructor", y_column="wins")
        assert Transformer().build_control_payload(_f1_rows(), m) is None

    def test_scrub_builds_one_slice_per_value(self):
        p = _payload([ControlSpec(column="year", kind="scrub")])
        assert p["scrub_column"] == "year"
        assert list(p["slices"].keys()) == ["1965", "1966", "1967"]
        assert p["default"] == "1967"                 # newest by default
        spec = next(c for c in p["controls"] if c["kind"] == "scrub")
        assert spec["values"] == ["1965", "1966", "1967"]

    def test_each_slice_is_a_valid_aggregated_chart(self):
        p = _payload([ControlSpec(column="year", kind="scrub")])
        slice_67 = {d["x"]: d["y"] for d in p["slices"]["1967"]}
        assert slice_67["Brabham"] == 9.0            # 3 rows * 3 wins summed
        assert slice_67["Lotus"] == 4.0
        assert slice_67["Cooper"] == 0.0

    def test_min_control_reports_measure_bounds(self):
        p = _payload([ControlSpec(column="year", kind="scrub"),
                      ControlSpec(column="wins", kind="min")])
        m = next(c for c in p["controls"] if c["kind"] == "min")
        assert m["min"] == 0
        assert m["max"] >= 9                          # covers Brabham's 9 in 1967
        assert m["label"] == "Minimum Wins"

    def test_unknown_column_control_is_ignored(self):
        p = _payload([ControlSpec(column="nonexistent", kind="scrub")])
        assert p is None

    def test_scrub_values_sorted_numerically(self):
        rows = [{"year": y, "constructor": "L", "wins": "1"} for y in ["9", "10", "2"]]
        m = AxisMapping(chart_type="bar", x_column="constructor", y_column="wins",
                        controls=[ControlSpec(column="year", kind="scrub")])
        p = Transformer().build_control_payload(rows, m)
        assert list(p["slices"].keys()) == ["2", "9", "10"]   # numeric, not lexical
