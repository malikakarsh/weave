"""A cumulative/standings measure is a running total, not an additive fact — the
mapper flips a plain 'sum' to 'max' (the terminal value) so it isn't double-counted
across the rows it repeats on."""

from pipeline.llm_mapper import _is_cumulative_measure, _prefer_terminal_agg


class TestCumulativeDetection:
    def test_standings_columns_detected(self):
        assert _is_cumulative_measure("constructor_standings_wins")
        assert _is_cumulative_measure("constructorStandingsPoints")
        assert _is_cumulative_measure("driver_standings_position")
        assert _is_cumulative_measure("cumulative_sales")
        assert _is_cumulative_measure("running_total")
        assert _is_cumulative_measure("career_points")

    def test_additive_columns_not_detected(self):
        assert not _is_cumulative_measure("wins")           # race wins — additive
        assert not _is_cumulative_measure("revenue")
        assert not _is_cumulative_measure("price")
        assert not _is_cumulative_measure("points")         # per-race points — additive
        assert not _is_cumulative_measure("count")

    def test_token_boundary_avoids_false_positives(self):
        # 'outstanding' / 'understanding' contain 'standing' as a substring but not a token
        assert not _is_cumulative_measure("outstanding_balance")
        assert not _is_cumulative_measure("understanding_score")


class TestAggregationOverride:
    def test_sum_on_cumulative_becomes_max(self):
        data = {"y_column": "constructor_standings_wins", "aggregation": "sum"}
        _prefer_terminal_agg(data)
        assert data["aggregation"] == "max"

    def test_sum_on_additive_stays_sum(self):
        data = {"y_column": "revenue", "aggregation": "sum"}
        _prefer_terminal_agg(data)
        assert data["aggregation"] == "sum"

    def test_explicit_mean_is_respected(self):
        # only 'sum' is overridden — an explicit mean/count/min/max is left as asked
        data = {"y_column": "constructor_standings_wins", "aggregation": "mean"}
        _prefer_terminal_agg(data)
        assert data["aggregation"] == "mean"
