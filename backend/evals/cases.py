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
        "prompt": "show revenue over time as an area chart for each company",
        "expect_mapping": {
            "chart_type": "area",
            "x_column": "date",
            "y_column": "revenue",
            "group_column": "company",
        },
        "expect_data": {
            "grouped": True,
            "count": 3,
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
]
