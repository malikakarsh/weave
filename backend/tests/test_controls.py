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

    def test_threshold_field_matches_named_column(self):
        # A threshold slider filters the value of the column it NAMES, not always the
        # y measure — so 'minimum sepal length' (the x-axis) filters x, bounded by
        # the length column's max, not the width measure.
        rows = [{"len": str(L), "wid": str(W)} for L, W in
                [(4.6, 3.6), (5.7, 4.1), (7.9, 3.8)]]
        m = AxisMapping(chart_type="scatter", x_column="len", y_column="wid",
                        controls=[ControlSpec(column="len", kind="min"),
                                  ControlSpec(column="wid", kind="max")])
        p = Transformer().build_control_payload(rows, m)
        by_col = {c["column"]: c for c in p["controls"]}
        assert by_col["len"]["field"] == "x"
        assert by_col["len"]["max"] >= 7          # bounded by sepal LENGTH (~7.9)
        assert by_col["wid"]["field"] == "y"
        assert by_col["wid"]["max"] >= 4 and by_col["wid"]["max"] < 7   # by WIDTH (~4.1)

    def test_max_control_and_range_pair(self):
        # a max threshold, and a min+max pair on the same column (a range)
        p = _payload([ControlSpec(column="year", kind="scrub"),
                      ControlSpec(column="wins", kind="min"),
                      ControlSpec(column="wins", kind="max")])
        kinds = [c["kind"] for c in p["controls"]]
        assert "min" in kinds and "max" in kinds
        mx = next(c for c in p["controls"] if c["kind"] == "max")
        assert mx["label"] == "Maximum Wins"
        assert mx["min"] == 0 and mx["max"] >= 9

    def test_dropdown_control_slices_like_scrub(self):
        # A dropdown is scrub slicing with a <select> UI — same slices, kind preserved.
        p = _payload([ControlSpec(column="year", kind="dropdown")])
        assert list(p["slices"].keys()) == ["1965", "1966", "1967"]
        spec = next(c for c in p["controls"] if c["kind"] == "dropdown")
        assert spec["values"] == ["1965", "1966", "1967"]

    def test_default_skips_empty_slice(self):
        # The newest bucket (2024) has rows but its measure is all-null and a filter
        # drops them, so its slice transforms to empty — the default must fall back
        # to the newest slice that actually has data (2023).
        from models.spec import FilterSpec
        rows = ([{"year": y, "team": t, "points": "25"}
                 for y in ("2022", "2023") for t in ("A", "B")]
                + [{"year": "2024", "team": t, "points": ""} for t in ("A", "B")])
        m = AxisMapping(chart_type="bar", x_column="team", y_column="points",
                        aggregation="sum", filters=[FilterSpec(column="points", min="0")],
                        controls=[ControlSpec(column="year", kind="dropdown")])
        p = Transformer().build_control_payload(rows, m)
        assert p["default"] == "2023"                 # not the empty 2024
        assert "2024" in p["slices"] and p["slices"]["2024"] == []   # still selectable

    def test_network_min_is_a_degree_connections_filter(self):
        # "minimum connections" on a network has no column — a threshold on a
        # node-identity column (x/y) means node DEGREE. The control is labelled
        # "Connections", bounded by the busiest node, and nodes carry their degree.
        rows = [{"race": r, "team": t} for r in ["A", "B", "C"] for t in ["Ferrari", "RedBull"]]
        rows.append({"race": "A", "team": "Sauber"})            # degree-1 node
        m = AxisMapping(chart_type="network", x_column="race", y_column="team",
                        controls=[ControlSpec(column="race", kind="min")])
        p = Transformer().build_control_payload(rows, m)
        c = p["controls"][0]
        assert c["field"] == "degree"
        assert c["label"] == "Minimum Connections"
        assert c["max"] == 3                                    # Ferrari/RedBull hit 3 races
        graph = Transformer().transform(rows, m)                # nodes carry their degree
        degrees = {n["id"]: n["degree"] for n in graph["nodes"]}
        assert degrees["Ferrari"] == 3 and degrees["Sauber"] == 1

    def test_network_connections_uses_virtual_column(self):
        # The normalizer rewrites a network degree filter borrowed onto an identity
        # column into the stable virtual column 'connections', so it's referenceable
        # by name (e.g. "remove the connections filter") and distinct from a real
        # z-column threshold on the same graph.
        from pipeline.llm_mapper import _normalize_network_connections
        data = {"chart_type": "network", "x_column": "team", "y_column": "race",
                "z_column": "points",
                "controls": [{"column": "team", "kind": "min"},
                             {"column": "points", "kind": "max"}]}
        _normalize_network_connections(data)
        cols = [(c["column"], c["kind"]) for c in data["controls"]]
        assert cols == [("connections", "min"), ("points", "max")]

    def test_network_virtual_connections_builds_degree_control(self):
        rows = [{"team": t, "race": r} for r in ["A", "B", "C"] for t in ["Ferrari", "RedBull"]]
        rows.append({"team": "Sauber", "race": "A"})
        m = AxisMapping(chart_type="network", x_column="team", y_column="race",
                        controls=[ControlSpec(column="connections", kind="min")])
        p = Transformer().build_control_payload(rows, m)
        c = p["controls"][0]
        assert c["column"] == "connections" and c["field"] == "degree"
        assert c["label"] == "Minimum Connections" and c["max"] == 3

    def test_network_value_threshold_carries_owning_side(self):
        # A network value threshold applies to only ONE side (the entity the measure
        # describes = the source/x side), tagged so the client keeps the other side as
        # context instead of hiding it under a mismatched size cutoff.
        rows = [{"team": t, "race": r, "points": "50"}
                for r in ["A", "B"] for t in ["RedBull", "Sauber"]]
        m = AxisMapping(chart_type="network", x_column="team", y_column="race",
                        x_label="Constructor", z_column="points",
                        controls=[ControlSpec(column="points", kind="min")])
        c = Transformer().build_control_payload(rows, m)["controls"][0]
        assert c["field"] == "measure" and c["side"] == "Constructor"

    def test_network_value_filter_adopts_weight_not_degree(self):
        # A numeric VALUE threshold on a network (e.g. a points filter) must NOT be
        # mistaken for a connections/degree filter. It filters node size, so the
        # column is adopted as the graph weight and the control is a value measure.
        from pipeline.llm_mapper import _normalize_network_connections
        data = {"chart_type": "network", "x_column": "team", "y_column": "race",
                "z_column": None,
                "controls": [{"column": "points", "kind": "min"}]}
        _normalize_network_connections(data)
        assert data["z_column"] == "points"                # weighted so nodes carry it
        assert data["controls"][0]["column"] == "points"   # NOT rewritten to connections
        rows = [{"team": t, "race": r, "points": str(p)}
                for r in ["A", "B"] for t, p in [("RedBull", 50), ("Sauber", 1)]]
        m = AxisMapping(chart_type="network", x_column="team", y_column="race",
                        z_column="points", controls=[ControlSpec(column="points", kind="min")])
        c = Transformer().build_control_payload(rows, m)["controls"][0]
        assert c["field"] == "measure" and c["label"] == "Minimum Points"

    def test_dropdown_composes_with_scrub(self):
        # a dropdown + a scrub on different columns compose into one composite slice key
        rows = []
        for team in ["A", "B"]:
            for yr in ["2020", "2021"]:
                rows.append({"team": team, "year": yr, "x": "c", "wins": "1"})
        m = AxisMapping(chart_type="bar", x_column="x", y_column="wins", aggregation="count",
                        controls=[ControlSpec(column="team", kind="dropdown"),
                                  ControlSpec(column="year", kind="scrub")])
        p = Transformer().build_control_payload(rows, m)
        kinds = sorted(c["kind"] for c in p["controls"])
        assert kinds == ["dropdown", "scrub"]
        sep = p["scrub_sep"]
        assert sep.join(["A", "2020"]) in p["slices"]

    def test_unknown_column_control_is_ignored(self):
        p = _payload([ControlSpec(column="nonexistent", kind="scrub")])
        assert p is None

    def test_scrub_on_categorical_x_is_dropped(self):
        # Scrubbing a CATEGORICAL x-axis is degenerate (one category per slice) — dropped.
        rows = [{"cut": c, "price": "100"} for c in ["A", "B", "C", "A", "B"]]
        m = AxisMapping(chart_type="bar", x_column="cut", y_column="price",
                        aggregation="sum",
                        controls=[ControlSpec(column="cut", kind="scrub")])
        assert Transformer().build_control_payload(rows, m) is None

    def test_scrub_on_temporal_x_windows_the_axis(self):
        # Scrubbing a CONTINUOUS/temporal x windows it: one slice per period,
        # window_x flags the template to rescale the axis to the current slice.
        rows = [{"date": f"2023-{mo:02d}-15", "revenue": "100"} for mo in range(1, 7)]
        m = AxisMapping(chart_type="line", x_column="date", y_column="revenue",
                        aggregation="sum",
                        controls=[ControlSpec(column="date", kind="scrub", time_unit="month")])
        p = Transformer().build_control_payload(rows, m)
        assert p is not None and p["window_x"] is True
        assert list(p["slices"].keys()) == [f"2023-{mo:02d}" for mo in range(1, 7)]

    def test_min_on_x_axis_column_still_works(self):
        # only scrub is positional; a min threshold on any column is fine
        rows = [{"cut": c, "price": str(p)} for c, p in
                [("A", 100), ("B", 200), ("C", 300)]]
        m = AxisMapping(chart_type="bar", x_column="cut", y_column="price",
                        aggregation="sum",
                        controls=[ControlSpec(column="price", kind="min")])
        p = Transformer().build_control_payload(rows, m)
        assert p is not None and p["controls"][0]["kind"] == "min"

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
