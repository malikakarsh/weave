"""
UAT eval cases for the Weave pipeline.

Each case tests the full LLM mapping + transformer stack.

expect_mapping: fields to assert on the AxisMapping the LLM returns.
  - Omit a field to skip checking it.
  - Use None explicitly only if you expect the field to be None.

expect_data: assertions on the transformer output.
  - count: expected number of top-level items (groups or flat rows)
  - grouped: True if output is [{group, values}], False if [{x, y}]
  - values_count: for grouped output, expected len of values per group
    (can be a single int meaning "all groups have this many values")
  - spot: list of {x, y} pairs to find anywhere in the flat or nested output
  - x_includes: list of x values that must appear
  - x_excludes: list of x values that must NOT appear (dirty data checks)
"""

CASES = [
    # ------------------------------------------------------------------ #
    # Chart type selection
    # ------------------------------------------------------------------ #
    {
        "name": "line: trend over time",
        "csv": "samples/sample.csv",
        "prompt": "show me revenue over time",
        "expect_mapping": {
            "chart_type": "line",
            "x_column": "date",
            "y_column": "revenue",
        },
        # LLM may or may not group by company — both are valid for this prompt
        "expect_data": {},
    },
    {
        "name": "area: explicit area chart request",
        "csv": "samples/sample.csv",
        "prompt": "show Acme revenue over time as an area chart",
        "expect_mapping": {
            "chart_type": "area",
            "x_column": "date",
            "y_column": "revenue",
        },
        "stub_mapping": {
            "chart_type": "area",
            "x_column": "date",
            "y_column": "revenue",
            "group_column": "company",
            "group_filter": ["Acme"],
            "aggregation": "sum",
            "sort_order": "none",
        },
        "expect_data": {
            "grouped": True,
            "count": 1,
        },
    },
    {
        "name": "bar: categorical x-axis",
        "csv": "samples/sample.csv",
        "prompt": "show total revenue per company",
        "expect_mapping": {
            "chart_type": "bar",
            "x_column": "company",
            "y_column": "revenue",
            "aggregation": "sum",
        },
        "expect_data": {
            "grouped": False,
            "count": 3,
        },
    },
    {
        "name": "scatter: two numeric axes",
        "csv": "samples/iris.csv",
        "prompt": "show sepal length vs sepal width as a scatter plot",
        "expect_mapping": {
            "chart_type": "scatter",
            "x_column": "SepalLengthCm",
            "y_column": "SepalWidthCm",
        },
        "expect_data": {
            "grouped": False,
        },
    },
    {
        "name": "box_plot: sepal length distribution by species",
        "csv": "samples/iris.csv",
        "prompt": "show the distribution of sepal length by species as a box plot",
        "expect_mapping": {
            "chart_type": "box_plot",
        },
        # Full stub so --fast can build the mapping and exercise the box transform.
        "stub_mapping": {
            "chart_type": "box_plot",
            "x_column": "Species",
            "y_column": "SepalLengthCm",
        },
        "expect_data": {
            "grouped": False,
            "count": 3,
            "x_includes": ["Iris-setosa", "Iris-versicolor", "Iris-virginica"],
        },
    },

    # ------------------------------------------------------------------ #
    # Aggregation function
    # ------------------------------------------------------------------ #
    {
        "name": "agg: count — number of inspections",
        "csv": "samples/nyc_restaurants.csv",
        "prompt": "show the number of inspections per borough",
        "expect_mapping": {
            "chart_type": "bar",
            "x_column": "boro",
            "aggregation": "count",
        },
        "expect_data": {
            "grouped": False,
        },
    },
    {
        "name": "agg: mean — average sepal length per species",
        "csv": "samples/iris.csv",
        "prompt": "what is the average sepal length per species?",
        "expect_mapping": {
            "chart_type": "bar",
            "x_column": "Species",
            "y_column": "SepalLengthCm",
            "aggregation": "mean",
        },
        "expect_data": {
            "grouped": False,
            "count": 3,
        },
    },
    {
        "name": "agg: sum — total revenue per company",
        "csv": "samples/sample.csv",
        "prompt": "total revenue per company",
        "expect_mapping": {
            "aggregation": "sum",
            "x_column": "company",
            "y_column": "revenue",
        },
        "expect_data": {
            "grouped": False,
            "count": 3,
            # Acme sum across 12 months
            "spot": [{"x": "Acme", "y": 264803.5}],
        },
    },

    # ------------------------------------------------------------------ #
    # Group column + filter
    # ------------------------------------------------------------------ #
    {
        "name": "group: multi-series by company",
        "csv": "samples/sample.csv",
        "prompt": "compare revenue across all companies over time",
        "expect_mapping": {
            "chart_type": "line",
            "x_column": "date",
            "y_column": "revenue",
            "group_column": "company",
        },
        "expect_data": {
            "grouped": True,
            "count": 3,
            "values_count": 12,
        },
    },
    {
        "name": "group filter: single company",
        "csv": "samples/sample.csv",
        "prompt": "show me Acme revenue over time",
        "expect_mapping": {
            "x_column": "date",
            "y_column": "revenue",
            "group_column": "company",
            "group_filter": ["Acme"],
        },
        "expect_data": {
            "grouped": True,
            "count": 1,
            "values_count": 12,
        },
    },
    {
        "name": "group filter: two specific stocks",
        "csv": "samples/stocks.csv",
        "prompt": "compare AAPL and MSFT price over time",
        "expect_mapping": {
            "x_column": "date",
            "y_column": "price",
            "group_column": "symbol",
            "group_filter": ["AAPL", "MSFT"],
        },
        "expect_data": {
            "grouped": True,
            "count": 2,
        },
    },

    # ------------------------------------------------------------------ #
    # Top N
    # ------------------------------------------------------------------ #
    {
        "name": "top_n: top 5 boroughs",
        "csv": "samples/nyc_restaurants.csv",
        "prompt": "show the top 5 boroughs by number of inspections",
        "expect_mapping": {
            "top_n": 5,
            "aggregation": "count",
        },
        "expect_data": {
            "grouped": False,
            "count": 5,
        },
    },
    {
        "name": "top_n: top 3 companies by revenue",
        "csv": "samples/sample.csv",
        "prompt": "top 3 companies by total revenue",
        "expect_mapping": {
            "top_n": 3,
            "aggregation": "sum",
        },
        "expect_data": {
            "grouped": False,
            "count": 3,
        },
    },
    {
        # Column-referenced limit on the x-axis dimension of a grouped chart —
        # "top three colors" must limit the x-axis 'color' column, not the 'cut'
        # grouping. Verifies the transformer keeps exactly the top 3 colors.
        "name": "limit: top 3 colors of a grouped (color × cut) bar chart",
        "csv": "samples/diamonds.csv",
        "prompt": "grouped bar chart of average price with color on the x-axis and cut as the group",
        "refine_from": {
            "chart_type": "bar",
            "x_column": "color",
            "y_column": "price",
            "group_column": "cut",
            "aggregation": "mean",
        },
        "refine_instruction": "only the top three colors",
        "expect_mapping": {
            "limit": {"column": "color", "n": 3},
        },
        "expect_data": {
            "grouped": True,
            "values_count": 3,
            "x_includes": ["H", "I", "J"],
            "x_excludes": ["D", "E", "F", "G"],
        },
    },

    # ------------------------------------------------------------------ #
    # Sort order
    # ------------------------------------------------------------------ #
    {
        "name": "sort: bar chart uses asc or desc (not none)",
        "csv": "samples/sample.csv",
        "prompt": "show total revenue per company as a bar chart",
        "expect_mapping": {
            "chart_type": "bar",
            # LLM may choose asc or desc for revenue — both are valid; just must not be 'none'
        },
        "expect_data": {"grouped": False},
    },
    {
        "name": "sort: desc for top/highest",
        "csv": "samples/nyc_restaurants.csv",
        "prompt": "which boroughs have the highest number of inspections?",
        "expect_mapping": {
            "sort_order": "desc",
        },
        "expect_data": {"grouped": False},
    },
    {
        "name": "sort: none for line chart",
        "csv": "samples/sample.csv",
        "prompt": "show revenue over time",
        "expect_mapping": {
            "chart_type": "line",
            "sort_order": "none",
        },
        "expect_data": {},
    },

    # ------------------------------------------------------------------ #
    # Date bucketing (time_unit)
    # ------------------------------------------------------------------ #
    {
        "name": "time_unit: year",
        "csv": "samples/nyc_restaurants.csv",
        "prompt": "how has the number of inspections changed per year?",
        "expect_mapping": {
            "time_unit": "year",
            "aggregation": "count",
        },
        "stub_mapping": {
            "chart_type": "line",
            "x_column": "inspection_date",
            "y_column": "record_date",
            "time_unit": "year",
            "aggregation": "count",
        },
        "expect_data": {
            "grouped": False,
            # 1900 dirty sentinel will appear as "1900-01-01" since no date filter is applied
            "x_includes": ["2024-01-01", "2023-01-01"],
        },
    },
    {
        "name": "time_unit: month — grouped",
        "csv": "samples/sample.csv",
        "prompt": "what is the average monthly revenue for each company?",
        "expect_mapping": {
            "time_unit": "month",
            "aggregation": "mean",
            "group_column": "company",
        },
        "stub_mapping": {
            "chart_type": "line",
            "x_column": "date",
            "y_column": "revenue",
            "time_unit": "month",
            "aggregation": "mean",
            "group_column": "company",
        },
        "expect_data": {
            "grouped": True,
            "count": 3,
            "values_count": 12,
        },
    },

    # ------------------------------------------------------------------ #
    # Date range filtering (x_min / x_max)
    # ------------------------------------------------------------------ #
    {
        "name": "x_range: from March to September",
        "csv": "samples/sample.csv",
        "prompt": "show Acme revenue from March to September",
        "expect_mapping": {
            "group_column": "company",
            "group_filter": ["Acme"],
        },
        "expect_data": {
            "grouped": True,
            "count": 1,
            "values_count": 7,
            "x_excludes": ["2024-01-01", "2024-02-01", "2024-10-01", "2024-11-01", "2024-12-01"],
        },
    },
    {
        "name": "x_range: inspections between 2022 and 2024",
        "csv": "samples/nyc_restaurants.csv",
        "prompt": "how many inspections happened per year between 2022 and 2024?",
        "expect_mapping": {
            "time_unit": "year",
            "aggregation": "count",
        },
        "expect_data": {
            "grouped": False,
            "count": 3,
            "x_includes": ["2022-01-01", "2023-01-01", "2024-01-01"],
            "x_excludes": ["1900-01-01", "2025-01-01"],
        },
    },

    # ------------------------------------------------------------------ #
    # Stacked area chart
    # ------------------------------------------------------------------ #
    {
        "name": "stacked_area: revenue composition over time by company",
        "csv": "samples/sample.csv",
        "prompt": "show a stacked area chart of revenue over time for each company",
        "expect_mapping": {
            "chart_type": "stacked_area",
            "x_column": "date",
            "y_column": "revenue",
            "group_column": "company",
            "sort_order": "none",
        },
        "expect_data": {
            "grouped": True,
        },
    },

    # ------------------------------------------------------------------ #
    # Stacked bar chart
    # ------------------------------------------------------------------ #
    {
        "name": "stacked_bar: monthly revenue by company",
        "csv": "samples/sample.csv",
        "prompt": "show a stacked bar chart of monthly revenue for each company",
        "expect_mapping": {
            "chart_type": "stacked_bar",
            "x_column": "date",
            "y_column": "revenue",
            "group_column": "company",
            "time_unit": "month",
        },
        "expect_data": {
            "grouped": True,
            "count": 3,
            "values_count": 12,
        },
    },

    # ------------------------------------------------------------------ #
    # Pie chart
    # ------------------------------------------------------------------ #
    {
        "name": "pie: revenue breakdown by company",
        "csv": "samples/sample.csv",
        "prompt": "show the revenue breakdown by company as a pie chart",
        "expect_mapping": {
            "chart_type": "pie",
            "x_column": "company",
            "y_column": "revenue",
            "aggregation": "sum",
        },
        "expect_data": {
            "grouped": False,
            "count": 3,
            "spot": [{"x": "Acme", "y": 264803.5}],
        },
    },
    {
        "name": "pie: share of inspections by borough",
        "csv": "samples/nyc_restaurants.csv",
        "prompt": "show the share of inspections by borough",
        "expect_mapping": {
            "chart_type": "pie",
            "x_column": "boro",
            "aggregation": "count",
        },
        "expect_data": {
            "grouped": False,
        },
    },

    # ------------------------------------------------------------------ #
    # Bubble chart
    # ------------------------------------------------------------------ #
    {
        "name": "bubble: sepal vs petal sized by petal length",
        "csv": "samples/iris.csv",
        "prompt": "show a bubble chart of sepal length vs sepal width sized by petal length for each species",
        "expect_mapping": {
            "chart_type": "bubble",
            "x_column": "SepalLengthCm",
            "y_column": "SepalWidthCm",
            "z_column": "PetalLengthCm",
            "group_column": "Species",
        },
        "expect_data": {
            "grouped": True,
            "count": 3,
            # Each species has many unique SepalLengthCm values — transformer buckets by x,
            # so values_count varies (~15-21 per species). Just assert 3 groups.
        },
    },

    # ------------------------------------------------------------------ #
    # Network graph
    # ------------------------------------------------------------------ #
    {
        "name": "network: airport routes weighted by distance",
        "csv": "samples/airport_routes.csv",
        "prompt": "show a network graph of airport routes weighted by distance",
        "expect_mapping": {
            "chart_type": "network",
            "x_column": "source",
            "y_column": "target",
            "z_column": "distance_km",
        },
        "expect_data": {
            "nodes_count": 9,
            "links_count": 20,
            "node_ids": ["JFK", "LAX", "ORD", "ATL", "SFO"],
        },
    },
    {
        "name": "network: unweighted airport connections",
        "csv": "samples/airport_routes.csv",
        "prompt": "show connections between airports as a network graph",
        "expect_mapping": {
            "chart_type": "network",
            "x_column": "source",
            "y_column": "target",
        },
        "expect_data": {
            "nodes_count": 9,
            "links_count": 20,
        },
    },

    # ------------------------------------------------------------------ #
    # Heatmap
    # ------------------------------------------------------------------ #
    {
        "name": "heatmap: average diamond price by cut and color",
        "csv": "samples/diamonds.csv",
        "prompt": "show a heatmap of average diamond price by cut and color",
        "expect_mapping": {
            "chart_type": "heatmap",
            "aggregation": "mean",
            # axis assignment (cut vs color on x/y) is arbitrary — don't assert specific order
        },
        "expect_data": {
            # heatmap transformer outputs flat [{x, y, z}] — not grouped
            "grouped": False,
            # 5 cuts × 7 colors = 35 cells (all combinations present in dataset)
            "count": 35,
        },
    },
    {
        "name": "heatmap: count inspections by borough and critical flag",
        "csv": "samples/nyc_restaurants.csv",
        "prompt": "heatmap of inspection count by borough and critical flag",
        "expect_mapping": {
            "chart_type": "heatmap",
            # axis assignment is arbitrary — just assert the right chart type
        },
        "expect_data": {
            "grouped": False,
        },
    },

    # ------------------------------------------------------------------ #
    # Facet (small multiples)
    # ------------------------------------------------------------------ #
    {
        "name": "facet: line small multiples by company",
        "csv": "samples/sample.csv",
        "prompt": "show revenue over time as a line chart with small multiples, one panel per company",
        "expect_mapping": {
            "chart_type": "line",
            "x_column": "date",
            "y_column": "revenue",
            "group_column": "company",
            "facet_direction": "columns",
        },
        "expect_data": {
            "grouped": True,
            "count": 3,
        },
    },
    {
        "name": "facet: scatter by species in rows",
        "csv": "samples/iris.csv",
        "prompt": "facet the sepal length vs sepal width scatter plot in rows, one row per species",
        "expect_mapping": {
            "chart_type": "scatter",
            "x_column": "SepalLengthCm",
            "y_column": "SepalWidthCm",
            "group_column": "Species",
            "facet_direction": "rows",
        },
        "expect_data": {
            "grouped": True,
            "count": 3,
        },
    },

    # ------------------------------------------------------------------ #
    # Symbol map
    # ------------------------------------------------------------------ #
    {
        "name": "symbol_map: world cities sized by population",
        "csv": "samples/world_cities.csv",
        "prompt": "plot world cities on a map, size each symbol by population and color by continent",
        "expect_mapping": {
            "chart_type": "symbol_map",
            "x_column": "longitude",
            "y_column": "latitude",
            "z_column": "population",
            "group_column": "continent",
        },
        "expect_data": {
            # symbol_map outputs flat [{x, y, z, group, ...}] — one point per row
            "count": 55,
        },
    },
    {
        "name": "symbol_map: cities labeled",
        "csv": "samples/world_cities.csv",
        "prompt": "show a world map of cities with population as bubble size, label each city",
        "expect_mapping": {
            "chart_type": "symbol_map",
            "x_column": "longitude",
            "y_column": "latitude",
            "z_column": "population",
            "label_column": "city",
        },
        "expect_data": {
            "count": 55,
        },
    },

    # ------------------------------------------------------------------ #
    # Combined: multiple features at once
    # ------------------------------------------------------------------ #
    {
        "name": "combined: top 5 + date range + count",
        "csv": "samples/nyc_restaurants.csv",
        "prompt": "top 5 neighborhoods by inspections between 2022 and 2024",
        "expect_mapping": {
            "top_n": 5,
            "aggregation": "count",
        },
        "expect_data": {
            "grouped": False,
            "count": 5,
        },
    },
    {
        "name": "combined: stocks average per year grouped",
        "csv": "samples/stocks.csv",
        "prompt": "show average stock price per year for each company",
        "expect_mapping": {
            "group_column": "symbol",
            "aggregation": "mean",
            "time_unit": "year",
            "sort_order": "none",
        },
        "expect_data": {
            "grouped": True,
        },
    },

    # ------------------------------------------------------------------ #
    # Box plot fallback
    # ------------------------------------------------------------------ #
    {
        "name": "box plot fallback: request box plot → bar + mean",
        "csv": "samples/diamonds.csv",
        "prompt": "show a box plot of diamond price distribution by cut",
        "expect_mapping": {
            "chart_type": "bar",
            "x_column": "cut",
            "y_column": "price",
            "aggregation": "mean",
        },
        "expect_data": {
            "grouped": False,
            "count": 5,
        },
    },
    {
        "name": "box plot fallback: violin request → bar",
        "csv": "samples/iris.csv",
        "prompt": "show a violin plot of sepal length per species",
        "expect_mapping": {
            "chart_type": "bar",
            "x_column": "Species",
            "y_column": "SepalLengthCm",
        },
        "expect_data": {
            "grouped": False,
            "count": 3,
        },
    },

    # ------------------------------------------------------------------ #
    # Refine cases
    # Each has a `refine_from` mapping and a `refine_instruction`.
    # The runner calls mapper.refine() instead of mapper.map().
    # ------------------------------------------------------------------ #
    {
        "name": "refine: sort descending",
        "csv": "samples/sample.csv",
        "prompt": "total revenue per company",
        "refine_from": {
            "chart_type": "bar",
            "x_column": "company",
            "y_column": "revenue",
            "aggregation": "sum",
            "sort_order": "asc",
        },
        "refine_instruction": "sort by descending",
        "expect_mapping": {
            "sort_order": "desc",
            "chart_type": "bar",
        },
        "expect_data": {},
    },
    {
        "name": "refine: sort ascending",
        "csv": "samples/sample.csv",
        "prompt": "total revenue per company",
        "refine_from": {
            "chart_type": "bar",
            "x_column": "company",
            "y_column": "revenue",
            "aggregation": "sum",
            "sort_order": "desc",
        },
        "refine_instruction": "sort ascending",
        "expect_mapping": {
            "sort_order": "asc",
            "chart_type": "bar",
        },
        "expect_data": {},
    },
    {
        "name": "refine: change overall color",
        "csv": "samples/sample.csv",
        "prompt": "total revenue per company",
        "refine_from": {
            "chart_type": "bar",
            "x_column": "company",
            "y_column": "revenue",
            "aggregation": "sum",
        },
        "refine_instruction": "change color to red",
        "expect_mapping": {
            "chart_type": "bar",
            # color should be set to some red value — checked by runner as non-null
        },
        "expect_mapping_custom": {
            "color_is_set": True,
        },
        "expect_data": {},
    },
    {
        # Mark-size refinement: "thinner bars" should reduce mark_scale below 1.0.
        # The exact multiplier is the LLM's call, so we assert a range, not a value.
        "name": "refine: thinner bars (mark size)",
        "csv": "samples/sample.csv",
        "prompt": "total revenue per company",
        "refine_from": {
            "chart_type": "bar",
            "x_column": "company",
            "y_column": "revenue",
            "aggregation": "sum",
        },
        "refine_instruction": "make the bars thinner",
        "expect_mapping": {
            "chart_type": "bar",
        },
        "expect_mapping_custom": {
            "mark_scale_lt": 1.0,
        },
        "expect_data": {},
    },
    {
        "name": "refine: per-category color",
        "csv": "samples/sample.csv",
        "prompt": "total revenue per company",
        "refine_from": {
            "chart_type": "bar",
            "x_column": "company",
            "y_column": "revenue",
            "aggregation": "sum",
        },
        "refine_instruction": "change Acme to yellow",
        "expect_mapping": {
            "chart_type": "bar",
        },
        "expect_mapping_custom": {
            "category_color_key": "Acme",
        },
        "expect_data": {},
    },
    {
        "name": "refine: change chart type",
        "csv": "samples/sample.csv",
        "prompt": "total revenue per company",
        "refine_from": {
            "chart_type": "bar",
            "x_column": "company",
            "y_column": "revenue",
            "aggregation": "sum",
        },
        "refine_instruction": "change to a pie chart",
        "expect_mapping": {
            "chart_type": "pie",
        },
        "expect_data": {},
    },
    {
        "name": "refine: reduce to top 5",
        "csv": "samples/nyc_restaurants.csv",
        "prompt": "show inspections by neighborhood",
        "refine_from": {
            "chart_type": "bar",
            "x_column": "dba",
            "y_column": "score",
            "aggregation": "count",
            "top_n": None,
        },
        "refine_instruction": "show only the top 5",
        "expect_mapping": {
            "top_n": 5,
        },
        "expect_data": {
            "grouped": False,
            "count": 5,
        },
    },
    {
        "name": "refine: add group filter",
        "csv": "samples/stocks.csv",
        "prompt": "show stock prices over time",
        "refine_from": {
            "chart_type": "line",
            "x_column": "date",
            "y_column": "price",
            "group_column": "symbol",
            "sort_order": "none",
        },
        "refine_instruction": "show only AAPL and MSFT",
        "expect_mapping": {
            "group_filter": ["AAPL", "MSFT"],
        },
        "expect_data": {
            "grouped": True,
            "count": 2,
        },
    },
    {
        "name": "refine: fields not mentioned stay unchanged",
        "csv": "samples/sample.csv",
        "prompt": "total revenue per company",
        "refine_from": {
            "chart_type": "bar",
            "x_column": "company",
            "y_column": "revenue",
            "aggregation": "sum",
            "sort_order": "desc",
            "top_n": 2,
        },
        "refine_instruction": "change color to blue",
        "expect_mapping": {
            "chart_type": "bar",
            "sort_order": "desc",
            "top_n": 2,
            "aggregation": "sum",
        },
        "expect_data": {},
    },
]
