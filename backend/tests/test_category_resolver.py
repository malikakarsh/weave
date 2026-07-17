from models import AxisMapping
from models.spec import FilterSpec
from pipeline.category_resolver import (
    resolve_term, resolve_references, apply_choice, Clarification,
)

CUTS = ["Ideal", "Premium", "Good", "Very Good", "Fair"]
REGIONS = ["North America", "North Africa", "Northern Europe", "South Asia"]


class TestResolveTerm:
    def test_exact_case_insensitive(self):
        assert resolve_term("good", CUTS) == ("exact", "Good")
        assert resolve_term("VERY GOOD", CUTS) == ("exact", "Very Good")

    def test_unique_fuzzy(self):
        assert resolve_term("america", REGIONS) == ("unique", "North America")

    def test_ambiguous(self):
        kind, opts = resolve_term("north", REGIONS)
        assert kind == "ambiguous"
        assert "North America" in opts and "North Africa" in opts

    def test_none_returns_closest(self):
        kind, opts = resolve_term("atlantis", REGIONS)
        assert kind == "none"
        assert opts  # closest suggestions provided

    def test_good_is_exact_not_ambiguous(self):
        # the reported bug: 'good' must resolve to Good, not to {Good, Very Good}
        assert resolve_term("good", CUTS) == ("exact", "Good")


def _rows(col, values):
    return [{col: v} for v in values]


class TestResolveReferences:
    def test_category_colors_exact_applied(self):
        m = AxisMapping(chart_type="bar", x_column="cut", y_column="price",
                        category_colors={"good": "#ff0"})
        res = resolve_references(m, _rows("cut", CUTS))
        assert res.mapping.category_colors == {"Good": "#ff0"}
        assert res.clarifications == []

    def test_category_colors_ambiguous_clarifies(self):
        m = AxisMapping(chart_type="bar", x_column="region", y_column="v",
                        category_colors={"north": "#ff0"})
        res = resolve_references(m, _rows("region", REGIONS))
        assert res.mapping.category_colors in (None, {})
        assert len(res.clarifications) == 1
        c = res.clarifications[0]
        assert c.field == "category_colors" and c.reason == "ambiguous" and c.color == "#ff0"

    def test_filters_resolved(self):
        m = AxisMapping(chart_type="bar", x_column="cut", y_column="price",
                        filters=[FilterSpec(column="cut", values=["premium", "ideal"])])
        res = resolve_references(m, _rows("cut", CUTS))
        assert res.mapping.filters[0].values == ["Premium", "Ideal"]
        assert res.clarifications == []

    def test_group_filter_ambiguous(self):
        m = AxisMapping(chart_type="bar", x_column="v", y_column="v",
                        group_column="region", group_filter=["north"])
        res = resolve_references(m, _rows("region", REGIONS))
        assert res.clarifications and res.clarifications[0].field == "group_filter"


class TestApplyChoice:
    def test_apply_category_color(self):
        m = AxisMapping(chart_type="bar", x_column="region", y_column="v")
        clar = Clarification(field="category_colors", term="north", column="region",
                             options=REGIONS, reason="ambiguous", color="#ff0")
        out = apply_choice(m, clar, "North America")
        assert out.category_colors == {"North America": "#ff0"}

    def test_apply_group_filter(self):
        m = AxisMapping(chart_type="bar", x_column="v", y_column="v", group_column="region")
        clar = Clarification(field="group_filter", term="north", column="region",
                             options=REGIONS, reason="ambiguous")
        out = apply_choice(m, clar, "North Africa")
        assert out.group_filter == ["North Africa"]
