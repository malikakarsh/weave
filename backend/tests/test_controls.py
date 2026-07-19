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

    def test_date_scrub_buckets_by_year_automatically(self):
        # Regression: a scrub on a raw DATE column must bucket by year, not build
        # one near-empty slice per exact timestamp.
        rows = []
        for date, boro in [("2022-03-01", "BK"), ("2022-07-15", "BK"), ("2022-07-15", "QN"),
                           ("2023-01-09", "BK"), ("2023-09-05", "QN")]:
            rows.append({"inspection_date": date, "boro": boro, "camis": "1"})
        m = AxisMapping(chart_type="bar", x_column="boro", y_column="camis",
                        aggregation="count",
                        controls=[ControlSpec(column="inspection_date", kind="scrub")])
        p = Transformer().build_control_payload(rows, m)
        assert list(p["slices"].keys()) == ["2022", "2023"]   # years, not timestamps
        assert p["default"] == "2023"
        by = {d["x"]: d["y"] for d in p["slices"]["2022"]}
        assert by == {"BK": 2.0, "QN": 1.0}

    def test_date_scrub_explicit_month_unit(self):
        rows = [{"d": d, "k": "A", "n": "1"} for d in
                ["2023-01-05", "2023-01-20", "2023-02-11"]]
        m = AxisMapping(chart_type="bar", x_column="k", y_column="n", aggregation="count",
                        controls=[ControlSpec(column="d", kind="scrub", time_unit="month")])
        p = Transformer().build_control_payload(rows, m)
        assert list(p["slices"].keys()) == ["2023-01", "2023-02"]

    def test_two_scrubs_year_and_month_on_one_date_column(self):
        # "add a year and a month slider" — two SEPARATE sliders; slices keyed by
        # (year, month-of-year) composite; default is the newest existing combo.
        rows = []
        for date, boro in [("2022-03-01", "BK"), ("2022-03-09", "QN"), ("2022-07-15", "BK"),
                           ("2023-01-09", "BK"), ("2023-09-05", "QN"), ("2023-09-20", "QN")]:
            rows.append({"inspection_date": date, "boro": boro, "camis": "1"})
        m = AxisMapping(chart_type="bar", x_column="boro", y_column="camis", aggregation="count",
                        controls=[ControlSpec(column="inspection_date", kind="scrub", time_unit="year"),
                                  ControlSpec(column="inspection_date", kind="scrub", time_unit="month")])
        p = Transformer().build_control_payload(rows, m)
        scrub_specs = [c for c in p["controls"] if c["kind"] == "scrub"]
        assert len(scrub_specs) == 2
        assert scrub_specs[0]["values"] == ["2022", "2023"]
        assert scrub_specs[1]["values"] == ["01", "03", "07", "09"]   # month-of-year
        assert scrub_specs[1]["label"] == "Month"
        sep = p["scrub_sep"]
        assert p["default"] == sep.join(["2023", "09"])              # newest existing combo
        by = {d["x"]: d["y"] for d in p["slices"][sep.join(["2023", "09"])]}
        assert by == {"QN": 2.0}

    def test_two_scrubs_auto_units_without_time_unit(self):
        # The LLM may omit time_unit — two scrubs on one date column auto-assign
        # year then month, so the deterministic path still yields two sliders.
        rows = [{"d": d, "k": "A", "n": "1"} for d in
                ["2022-03-01", "2022-07-15", "2023-01-09"]]
        m = AxisMapping(chart_type="bar", x_column="k", y_column="n", aggregation="count",
                        controls=[ControlSpec(column="d", kind="scrub"),
                                  ControlSpec(column="d", kind="scrub")])
        p = Transformer().build_control_payload(rows, m)
        scrub_specs = [c for c in p["controls"] if c["kind"] == "scrub"]
        assert scrub_specs[0]["values"] == ["2022", "2023"]
        assert scrub_specs[1]["values"] == ["01", "03", "07"]
