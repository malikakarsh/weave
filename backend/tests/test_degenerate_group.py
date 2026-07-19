"""Grouping by the x-axis column is degenerate (skinny sub-slot boxes + a legend
repeating the x labels) — the mapper converts it to a flat chart with a
per-category palette, which is what "make each <x> a different color" means."""

from pipeline.llm_mapper import _ungroup_degenerate


class TestUngroupDegenerate:
    def test_group_equal_x_dropped_and_palette_set(self):
        data = {"x_column": "cut", "group_column": "cut", "chart_type": "box_plot"}
        _ungroup_degenerate(data)
        assert data["group_column"] is None
        assert data["palette"] == "vibrant"

    def test_existing_colors_kept(self):
        data = {"x_column": "cut", "group_column": "cut",
                "category_colors": {"Ideal": "#f00"}}
        _ungroup_degenerate(data)
        assert data["group_column"] is None
        assert "palette" not in data          # explicit colors win

    def test_real_grouping_untouched(self):
        data = {"x_column": "cut", "group_column": "color"}
        _ungroup_degenerate(data)
        assert data["group_column"] == "color"
        assert "palette" not in data
