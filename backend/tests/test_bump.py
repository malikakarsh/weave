"""Bump chart: rankings of grouped series over an ordered period. The transformer
aggregates the measure per (group, period), then ranks the groups at each period
(highest value = rank 1) and attaches that rank for the template to plot."""

from models import AxisMapping, ColumnInfo, ColumnType, Schema
from pipeline.chart_requirements import validate_chart
from pipeline.transformer import Transformer


def _rows():
    rows = []
    seasons = {
        "2021": {"RedBull": 100, "Merc": 120, "Ferrari": 80},
        "2022": {"RedBull": 150, "Merc": 90, "Ferrari": 110},
        "2023": {"RedBull": 160, "Merc": 70, "Ferrari": 130},
    }
    for season, teams in seasons.items():
        for team, pts in teams.items():
            rows.append({"season": season, "team": team, "points": str(pts)})
    return rows


def _bump(**kw):
    d = dict(chart_type="bump", x_column="season", y_column="points",
             group_column="team", aggregation="sum")
    d.update(kw)
    return AxisMapping(**d)


def _ranks(result):
    return {s["group"]: {v["x"]: v["rank"] for v in s["values"]} for s in result}


class TestBumpTransform:
    def test_highest_value_is_rank_one(self):
        r = _ranks(Transformer().transform(_rows(), _bump()))
        assert r["Merc"]["2021"] == 1 and r["RedBull"]["2021"] == 2 and r["Ferrari"]["2021"] == 3
        assert r["RedBull"]["2022"] == 1                # RedBull overtakes
        assert r["RedBull"]["2023"] == 1 and r["Merc"]["2023"] == 3

    def test_periods_are_chronologically_ordered(self):
        result = Transformer().transform(_rows(), _bump())
        for s in result:
            xs = [v["x"] for v in s["values"]]
            assert xs == ["2021", "2022", "2023"]

    def test_each_point_keeps_its_measure(self):
        r = {s["group"]: {v["x"]: v["y"] for v in s["values"]}
             for s in Transformer().transform(_rows(), _bump())}
        assert r["RedBull"]["2023"] == 160.0

    def test_top_n_keeps_and_ranks_among_survivors(self):
        # Keep the 2 strongest teams by total; ranks among them are a clean 1..2.
        result = Transformer().transform(_rows(), _bump(top_n=2))
        groups = {s["group"] for s in result}
        assert groups == {"RedBull", "Ferrari"}          # Merc has the lowest total
        maxrank = max(v["rank"] for s in result for v in s["values"])
        assert maxrank == 2


class TestBumpControls:
    def test_picker_on_group_column_is_dropped(self):
        # A scrub/dropdown on the ranked series is degenerate — one entity is
        # trivially always rank 1 — so the control is dropped (no payload here).
        from models import ControlSpec
        m = _bump(controls=[ControlSpec(column="team", kind="dropdown")])
        assert Transformer().build_control_payload(_rows(), m) is None

    def test_picker_on_other_dimension_slices(self):
        from models import ControlSpec
        rows = [{"season": s, "team": t, "region": r, "points": "10"}
                for s in ("2020", "2021") for t in ("A", "B") for r in ("EU", "US")]
        m = _bump(controls=[ControlSpec(column="region", kind="dropdown")])
        p = Transformer().build_control_payload(rows, m)
        assert p and p["controls"][0]["kind"] == "dropdown"
        assert set(p["controls"][0]["values"]) == {"EU", "US"}


class TestBumpValidation:
    def _schema(self, *cols):
        return Schema(row_count=9, columns=[ColumnInfo(name=n, type=t, sample=["1"]) for n, t in cols])

    def test_valid_with_group_and_numeric_y(self):
        sch = self._schema(("season", ColumnType.STRING), ("team", ColumnType.STRING),
                           ("points", ColumnType.FLOAT))
        assert validate_chart(_bump(), sch) is None

    def test_rejected_without_a_group_dimension(self):
        # Only one categorical column (the x) — nothing to rank by.
        sch = self._schema(("season", ColumnType.STRING), ("points", ColumnType.FLOAT))
        err = validate_chart(_bump(group_column=None), sch)
        assert err and "rank" in err.lower() or "second categorical" in (err or "").lower()

    def test_rejected_with_non_numeric_measure(self):
        sch = self._schema(("season", ColumnType.STRING), ("team", ColumnType.STRING),
                           ("note", ColumnType.STRING))
        err = validate_chart(_bump(y_column="note"), sch)
        assert err and "numeric" in err.lower()
