import math
from datetime import datetime

from models import AxisMapping
from pipeline.numeric import parse_number

_DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%d/%m/%y",
    "%m/%d/%y",
    "%b %d %Y",
    "%B %d %Y",
]


def _parse_dt(s: str) -> datetime | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _to_float(s: str) -> float | None:
    """Parse a row value as float; return None if it can't be converted.
    Tolerates currency, thousands separators, percent and accounting negatives."""
    return parse_number(s)


def _pretty_col(col: str) -> str:
    """Human label for a raw column name: 'raceId' → 'Race', 'min_wins' → 'Min Wins'."""
    import re
    s = re.sub(r"[_\s]+", " ", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", col)).strip()
    s = re.sub(r"\bId\b", "", s, flags=re.IGNORECASE).strip()
    return s.title() or col


def _parse_comparable(s: str):
    """Return a datetime or float for range comparison, or the raw string."""
    d = _parse_dt(s)
    if d:
        return d
    n = parse_number(s)
    return n if n is not None else s


def _in_range(raw_x: str, x_min: str | None, x_max: str | None) -> bool:
    if not x_min and not x_max:
        return True
    val = _parse_comparable(raw_x)
    if x_min:
        lo = _parse_comparable(x_min)
        try:
            if val < lo:
                return False
        except TypeError:
            pass
    if x_max:
        hi = _parse_comparable(x_max)
        try:
            if val > hi:
                return False
        except TypeError:
            pass
    return True


def _truncate(s: str, unit: str) -> str | None:
    d = _parse_dt(s)
    if not d:
        return None
    if unit == "year":
        return f"{d.year}-01-01"
    if unit == "month":
        return d.strftime("%Y-%m-01")
    if unit == "day":
        return d.strftime("%Y-%m-%d")
    return s


class Transformer:
    def transform(self, rows: list[dict], mapping: AxisMapping) -> list[dict] | dict:
        rows = self._prefilter(rows, mapping)
        if mapping.chart_type == "network":
            return self._transform_network(rows, mapping)
        if mapping.chart_type == "heatmap":
            return self._transform_heatmap(rows, mapping)
        if mapping.chart_type == "symbol_map":
            return self._transform_map(rows, mapping)
        if mapping.chart_type in ("box_plot", "box"):
            return self._transform_box(rows, mapping)
        if mapping.chart_type == "violin":
            return self._transform_violin(rows, mapping)
        if mapping.chart_type == "histogram":
            return self._transform_histogram(rows, mapping)
        if mapping.chart_type in ("radar", "spider"):
            return self._transform_radar(rows, mapping)
        if mapping.chart_type == "bump":
            return self._transform_bump(rows, mapping)
        if mapping.label_column:
            return self._transform_labeled(rows, mapping)
        if mapping.group_column:
            return self._transform_grouped(rows, mapping)
        return self._transform_flat(rows, mapping)

    # ------------------------------------------------------------------
    # Interactive controls (client-side filter sliders)
    # ------------------------------------------------------------------

    def build_control_payload(self, rows: list[dict], mapping: AxisMapping) -> dict | None:
        """Pre-compute everything the browser needs to drive the filter sliders with
        NO server round-trip. For a `scrub` control the server runs the full pipeline
        once per distinct value of that column and ships the finished slices keyed by
        value; the slider just swaps which pre-built slice is shown. `min` controls
        ship only their bounds and are applied client-side to the current slice.

        Returns None when there are no controls, so callers can skip injection."""
        if not mapping.controls or not rows:
            return None
        cols = set(rows[0].keys())
        base = mapping.model_copy(update={"controls": None})  # avoid recursion

        # A scrub on the chart's own x-axis is special. On a CONTINUOUS/temporal x
        # it WINDOWS the axis — each slice rescales the x to its own period, so a
        # "month slider" shows one month spread across the panel (window_x=True). On
        # a CATEGORICAL x it's degenerate (one category per slice) and is dropped.
        x_col = mapping.x_column
        x_vals = [r.get(x_col, "").strip() for r in rows[:50] if r.get(x_col, "").strip()]
        x_continuous = bool(x_vals) and (
            all(_parse_dt(v) for v in x_vals) or all(_to_float(v) is not None for v in x_vals)
        )
        # Only the templates that rescale the x per slice support windowing — the
        # non-faceted line/area and the facet renderer (faceted line/area/scatter).
        faceted = bool(mapping.facet_direction) and mapping.chart_type in ("line", "area", "scatter")
        windowable_chart = faceted or (
            not mapping.facet_direction and mapping.chart_type in ("line", "area"))
        # 'scrub' (a slider) and 'dropdown' (a <select>) are the same slicing — one
        # pre-built slice per value — differing only in the UI widget the client renders.
        window_x = False
        scrubs = []
        for c in mapping.controls:
            if c.kind not in ("scrub", "dropdown") or c.column not in cols:
                continue
            # A picker on a bump chart's GROUP column is degenerate — slicing by the
            # ranked series leaves one entity that's trivially always rank 1. Drop it.
            if mapping.chart_type == "bump" and c.column == mapping.group_column:
                continue
            if c.column == x_col:
                # windowing only makes sense for the ordered/stepped scrub slider
                if c.kind == "scrub" and x_continuous and windowable_chart:
                    window_x = True
                    scrubs.append(c)
                # else: degenerate x-scrub (categorical x, a dropdown, or a chart
                # without windowing support) — drop it so the chart keeps its axis
            else:
                scrubs.append(c)
        scrubs = scrubs[:2]
        # 'connections' is a virtual column for a network degree filter — it has no
        # source column but is still a valid threshold.
        thresholds = [c for c in mapping.controls if c.kind in ("min", "max") and (
            c.column in cols or (mapping.chart_type == "network" and c.column == "connections"))]

        specs: list[dict] = []
        slices: dict[str, object] = {}
        default: str | None = None
        scrub_col: str | None = None
        SEP = "\x1f"   # composite-slice key separator (multi-scrub)

        if scrubs:
            scrub_col = scrubs[0].column
            # Build one key function per scrub dimension. DATE columns are bucketed
            # by a time unit — a raw-value scrub would produce one near-empty slice
            # per exact timestamp. Two scrubs on the SAME date column become a
            # hierarchy: first → year, second → month-of-year (separate Year and
            # Month sliders, e.g. "add a year and a month slider").
            date_seen: dict[str, int] = {}
            key_fns = []
            for c in scrubs:
                sample_vals = [r.get(c.column, "").strip() for r in rows[:50]
                               if r.get(c.column, "").strip()]
                is_date = bool(sample_vals) and all(_parse_dt(v) for v in sample_vals)
                nth = date_seen.get(c.column, 0)
                unit = c.time_unit if c.time_unit in ("year", "month", "day") else None
                if is_date and unit is None:
                    unit = ("year", "month", "day")[min(nth, 2)]
                if is_date:
                    date_seen[c.column] = nth + 1

                if is_date and unit:
                    # First scrub on a column keeps the full period prefix ("2023",
                    # "2023-09"); a REPEAT scrub extracts the sub-component so the
                    # sliders are independent (Month: "01".."12", Day: "01".."31").
                    span = {"year": (0, 4), "month": (5, 7) if nth else (0, 7),
                            "day": (8, 10) if nth else (0, 10)}[unit]
                    def fn(r, col=c.column, u=unit, s=span):
                        t = _truncate(r.get(col, "").strip(), u)
                        return t[s[0]:s[1]] if t else None
                    label = c.label or (unit.title() if nth else _pretty_col(c.column))
                else:
                    def fn(r, col=c.column):
                        return r.get(col, "").strip() or None
                    label = c.label or _pretty_col(c.column)
                key_fns.append(fn)
                specs.append({"column": c.column, "kind": c.kind, "label": label})

            # Bucket rows by the tuple of scrub keys; cap the combination count so a
            # pathological pairing can't explode the payload — drop the 2nd dimension.
            buckets: dict[tuple, list[dict]] = {}
            for r in rows:
                ks = tuple(fn(r) for fn in key_fns)
                if all(k is not None for k in ks):
                    buckets.setdefault(ks, []).append(r)
            if len(buckets) > 400 and len(key_fns) > 1:
                key_fns = key_fns[:1]
                specs = specs[:1]
                merged: dict[tuple, list[dict]] = {}
                for ks, rs in buckets.items():
                    merged.setdefault(ks[:1], []).extend(rs)
                buckets = merged

            # Per-dimension value lists (numeric-aware sort), each spec gets its own.
            def _sorted_vals(vals: set[str]) -> list[str]:
                nums = {v: _to_float(v) for v in vals}
                if all(n is not None for n in nums.values()):
                    return sorted(vals, key=lambda v: nums[v])
                return sorted(vals)
            dim_values = [
                _sorted_vals({ks[i] for ks in buckets}) for i in range(len(key_fns))
            ]
            for spec, vals in zip(specs, dim_values):
                spec["values"] = vals

            # Emit slices in dimension order so the payload is deterministic.
            orders = [{v: i for i, v in enumerate(vals)} for vals in dim_values]
            key_order = lambda ks: tuple(orders[i][k] for i, k in enumerate(ks))
            for ks in sorted(buckets, key=key_order):
                sub = buckets[ks]
                try:
                    slices[SEP.join(ks)] = self.transform(sub, base)
                except Exception:
                    slices[SEP.join(ks)] = [] if base.chart_type not in ("network",) else {"nodes": [], "links": []}

            # Default = the newest/highest combination whose SLICE actually has data,
            # so the chart never opens empty. A bucket can have rows yet transform to
            # nothing (e.g. the latest year's measure is all null and gets filtered),
            # so pick by the rendered slice, not just the raw bucket.
            def _slice_empty(sl) -> bool:
                if isinstance(sl, dict):
                    return not sl.get("nodes")
                return not sl
            if buckets:
                non_empty = [ks for ks in buckets if not _slice_empty(slices.get(SEP.join(ks)))]
                best = max(non_empty or list(buckets), key=key_order)
                default = SEP.join(best)
                for spec, k in zip(specs, best):
                    spec["default"] = k

        # Data the thresholds apply to (a scrub slice if present, else the whole chart)
        ref_data = slices.get(default) if default is not None else self.transform(rows, base)
        # Charts whose y is an AGGREGATE — a threshold on the y-column filters the
        # aggregated value, so its bound comes from the transformed payload.
        aggregating = base.chart_type in ("bar", "line", "area", "stacked_bar",
                                          "stacked_area", "pie")
        for c in thresholds:
            field = self._control_field(c, base)
            # Bound: node degree from the graph payload; aggregated measures from the
            # transformed payload; a raw coordinate (scatter x/y, bubble z, a map's
            # size) from the source column.
            if field == "degree":
                hi = self._degree_max(ref_data)
            elif field == "measure" or (field == "y" and aggregating):
                hi = self._measure_max(ref_data)
            else:
                hi = self._column_max(rows, c.column)
            hi = hi if hi and hi > 0 else 1.0
            step = 1.0 if float(hi).is_integer() and hi <= 50 else round(hi / 20, 2) or 1.0
            prefix = "Maximum" if c.kind == "max" else "Minimum"
            # A degree threshold has no column to name — it filters "connections".
            default_label = f"{prefix} Connections" if field == "degree" \
                else f"{prefix} {_pretty_col(c.column)}"
            spec = {
                "column": c.column, "kind": c.kind, "field": field,
                "label": c.label or default_label,
                "min": 0, "max": math.ceil(hi), "step": step,
            }
            # A network VALUE threshold describes ONE entity (e.g. constructor points),
            # so it applies only to that side's nodes — the source (x) side, matching
            # node.group. The other side stays as context. Without this, the threshold
            # would hide the whole opposite side whose derived sizes fall below it.
            if base.chart_type == "network" and field == "measure":
                spec["side"] = base.x_label or base.x_column
            specs.append(spec)

        if not specs:
            return None
        return {"controls": specs, "slices": slices, "scrub_column": scrub_col,
                "scrub_sep": SEP, "default": default, "window_x": window_x}

    @staticmethod
    def _control_field(c, mapping) -> str:
        """Which value a threshold control filters on, matching the fields the
        transformed marks carry: 'x'/'y'/'z' when the control names an axis column,
        else 'measure' (the aggregated y / bin count / node value). This is what
        makes a 'minimum sepal length' slider filter the x column, not the y."""
        ct = mapping.chart_type
        if ct == "network":
            # 'connections' (virtual) or a node-IDENTITY column (x/y source/target
            # names) → node DEGREE ("minimum connections"). Any other column is a
            # value threshold on the node's aggregated SIZE (its total edge weight) —
            # the "measure" field reads d.size and bounds by the node-size max. The
            # normalizer makes that filtered column the graph weight so nodes carry it.
            if c.column == "connections" or c.column in (mapping.x_column, mapping.y_column):
                return "degree"
            return "measure"
        if ct == "histogram":   # bins carry a count/value measure
            return "measure"
        if c.column == mapping.z_column:
            return "z"
        if c.column == mapping.x_column:
            return "x"
        if c.column == mapping.y_column:
            return "y"
        return "measure"

    @staticmethod
    def _distinct_sorted(rows: list[dict], col: str) -> list[str]:
        vals = {r.get(col, "").strip() for r in rows if r.get(col, "").strip()}
        nums = {v: _to_float(v) for v in vals}
        if all(n is not None for n in nums.values()):
            return sorted(vals, key=lambda v: nums[v])
        return sorted(vals)

    @staticmethod
    def _degree_max(data) -> float:
        """Largest node degree in a network payload, for a 'minimum connections'
        slider's upper bound."""
        if isinstance(data, dict):
            return float(max((n.get("degree", 0) for n in data.get("nodes", [])),
                             default=0))
        return 0.0

    @staticmethod
    def _measure_max(data) -> float:
        """Largest aggregated measure in a transformed chart payload, for a min
        slider's upper bound — handles flat/grouped lists and the network dict."""
        best = 0.0
        if isinstance(data, dict):  # network
            for n in data.get("nodes", []):
                for k in ("value", "size", "weight"):
                    if isinstance(n.get(k), (int, float)):
                        best = max(best, float(n[k]))
        elif isinstance(data, list):
            def _measure_of(d: dict) -> float | None:
                # mirror the client accessor: aggregated y, bin count, heatmap z
                for k in ("y", "count", "z"):
                    v = d.get(k)
                    if isinstance(v, (int, float)):
                        return float(v)
                return None
            for d in data:
                if not isinstance(d, dict):
                    continue
                mv = _measure_of(d)
                if mv is not None:
                    best = max(best, mv)
                for v in (d.get("values") or []):
                    mv = _measure_of(v) if isinstance(v, dict) else None
                    if mv is not None:
                        best = max(best, mv)
        return best

    @staticmethod
    def _column_max(rows: list[dict], col: str) -> float:
        best = 0.0
        for r in rows:
            f = _to_float(r.get(col, "").strip())
            if f is not None:
                best = max(best, f)
        return best

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prefilter(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """Apply column-referenced filters and a top-N limit at the row level.

        These target a dimension by naming its column, so 'top 3 colors' vs
        'top 3 cuts' is unambiguous regardless of which is the x-axis vs the
        grouping. Unknown columns are ignored (no-op) rather than dropping rows.
        """
        cols = set(rows[0].keys()) if rows else set()

        # Row filters. Multiple filters on the SAME column combine as OR (a value
        # is kept if it matches any of them); different columns combine as AND.
        # This means re-filtering the same dimension (e.g. year 2016 after 2013)
        # can never collapse to an empty intersection.
        by_col: dict[str, list[FilterSpec]] = {}
        for f in (mapping.filters or []):
            if f.column in cols:
                by_col.setdefault(f.column, []).append(f)

        for col, specs in by_col.items():
            def matches(val: str, specs=specs) -> bool:
                for f in specs:
                    if f.values and val in {v.strip() for v in f.values}:
                        return True
                    if (f.min is not None or f.max is not None) and val and _in_range(val, f.min, f.max):
                        return True
                return False
            rows = [r for r in rows if matches(r.get(col, "").strip())]

        # Top-N limit on a chosen column, ranked by the same aggregation as the chart.
        lim = mapping.limit
        if lim and lim.column in cols and lim.n > 0:
            agg = mapping.aggregation
            buckets: dict[str, list[float | None]] = {}
            for r in rows:
                key = r.get(lim.column, "").strip()
                if not key:
                    continue
                y = r.get(mapping.y_column, "").strip()
                buckets.setdefault(key, []).append(
                    1.0 if agg == "count" else (_to_float(y) if y else None)
                )
            ranked = sorted(buckets, key=lambda k: (self._agg(buckets[k], agg) or 0), reverse=True)
            keep = set(ranked[: lim.n])
            rows = [r for r in rows if r.get(lim.column, "").strip() in keep]

        return rows

    @staticmethod
    def _sort(data: list[dict], order: str) -> list[dict]:
        if order not in ("asc", "desc"):
            return data
        return sorted(data, key=lambda d: (d["y"] is None, d["y"] or 0), reverse=(order == "desc"))

    @staticmethod
    def _agg(values: list[float | None], func: str) -> float | None:
        non_null = [v for v in values if v is not None]
        if not non_null:
            return None
        if func == "mean":
            return sum(non_null) / len(non_null)
        if func == "count":
            return float(len(non_null))
        if func == "min":
            return min(non_null)
        if func == "max":
            return max(non_null)
        return sum(non_null)  # "sum" and anything else

    @staticmethod
    def _collapse_measure(values_in_order: list[float | None], func: str) -> float | None:
        """Reduce a measure to ONE representative for its group, correcting a grain
        mismatch — a coarse-grained column repeated across fine-grained rows (the BI
        'fan trap'). Deterministic and domain-agnostic (no column-name knowledge):

          • constant across the group   → an attribute; use that single value
          • non-decreasing in row order → a cumulative running total; use the
                                          terminal (max) value, e.g. season 'wins'
          • otherwise                   → a genuine per-row measure; apply `func`

        This is what stops 'sum'/'count' from multiplying a repeated season total by
        the number of underlying rows."""
        vals = [v for v in values_in_order if v is not None]
        if not vals:
            return None
        if len(set(vals)) == 1:
            return vals[0]
        if all(a <= b for a, b in zip(vals, vals[1:])):
            return max(vals)
        return Transformer._agg(vals, func)

    @staticmethod
    def _x_key(raw_x: str, time_unit: str | None) -> str | None:
        if not time_unit:
            return raw_x
        return _truncate(raw_x, time_unit)

    @staticmethod
    def _quantile(sorted_vals: list[float], p: float) -> float:
        """Linear-interpolation quantile, matching d3.quantile."""
        n = len(sorted_vals)
        if n == 1 or p <= 0:
            return sorted_vals[0]
        if p >= 1:
            return sorted_vals[-1]
        h = (n - 1) * p
        lo = int(h)
        frac = h - lo
        if lo + 1 < n:
            return sorted_vals[lo] + (sorted_vals[lo + 1] - sorted_vals[lo]) * frac
        return sorted_vals[lo]

    def _box_stats(self, values: list[float]) -> dict | None:
        """Five-number summary + Tukey outliers for a list of numeric values."""
        ys = sorted(values)
        if not ys:
            return None
        q1 = self._quantile(ys, 0.25)
        median = self._quantile(ys, 0.5)
        q3 = self._quantile(ys, 0.75)
        iqr = q3 - q1
        lo_fence = q1 - 1.5 * iqr
        hi_fence = q3 + 1.5 * iqr
        inliers = [v for v in ys if lo_fence <= v <= hi_fence]
        outliers = [v for v in ys if v < lo_fence or v > hi_fence]
        return {
            "q1": q1,
            "median": median,
            "q3": q3,
            "whisker_low": inliers[0] if inliers else ys[0],
            "whisker_high": inliers[-1] if inliers else ys[-1],
            "outliers": outliers,
            "mean": sum(ys) / len(ys),
            "count": len(ys),
        }

    def _transform_box(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """One box (five-number summary) per x category, optionally per group.

        Unlike the aggregating modes, this keeps the full distribution so the
        template can draw quartiles, whiskers, and outliers.
        """
        grouped = bool(mapping.group_column)
        buckets: dict[tuple[str, str | None], list[float]] = {}
        x_order: list[str] = []
        group_order: list[str] = []

        for row in rows:
            raw_x = row.get(mapping.x_column, "").strip()
            if not raw_x or not _in_range(raw_x, mapping.x_min, mapping.x_max):
                continue
            x = self._x_key(raw_x, mapping.time_unit) or raw_x
            g = row.get(mapping.group_column, "").strip() if grouped else None
            if grouped and not g:
                continue
            y = _to_float(row.get(mapping.y_column, "").strip())
            if y is None:
                continue
            key = (x, g)
            if key not in buckets:
                buckets[key] = []
                if x not in x_order:
                    x_order.append(x)
                if g and g not in group_order:
                    group_order.append(g)
            buckets[key].append(y)

        result = []
        for (x, g), values in buckets.items():
            stats = self._box_stats(values)
            if stats is None:
                continue
            entry = {"x": x, **stats}
            if grouped:
                entry["group"] = g
            result.append(entry)

        # Preserve first-seen x order, then group order within each x.
        result.sort(key=lambda e: (
            x_order.index(e["x"]),
            group_order.index(e["group"]) if grouped else 0,
        ))
        return result

    @staticmethod
    def _kde(values: list[float], sample_points: list[float], q1: float, q3: float) -> list[float]:
        """Gaussian kernel density estimate evaluated at each sample point.

        Bandwidth uses Silverman's rule of thumb, robust to spread via the IQR.
        """
        n = len(values)
        if n == 0:
            return [0.0] * len(sample_points)
        mean = sum(values) / n
        std = (sum((v - mean) ** 2 for v in values) / n) ** 0.5
        iqr = q3 - q1
        sigma = min(std, iqr / 1.34) if iqr > 0 else std
        if sigma <= 0:
            sigma = std if std > 0 else 1.0
        h = 0.9 * sigma * n ** (-0.2)
        if h <= 0:
            h = 1.0
        norm = 1.0 / (n * h * (2 * math.pi) ** 0.5)
        out = []
        for sp in sample_points:
            total = 0.0
            for v in values:
                u = (sp - v) / h
                total += math.exp(-0.5 * u * u)
            out.append(norm * total)
        return out

    def _transform_radar(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """Radar/spider: one polygon per entity across several metric axes.

        Wide format (metric_columns set): each listed numeric column is an axis;
        values are aggregated per group. Long format (no metric_columns): reuse
        the grouped/flat transform where x_column is the axis label.
        Output shape matches grouped charts: [{group, values:[{x, y}]}].
        """
        metrics = mapping.metric_columns
        grouped = bool(mapping.group_column)

        if not metrics:
            # Long format — x_column is the axis, group_column the series.
            return self._transform_grouped(rows, mapping) if grouped \
                else self._transform_flat(rows, mapping)

        # Wide format — melt the metric columns into axes and aggregate per group.
        buckets: dict[tuple[str | None, str], list[float | None]] = {}
        group_order: list[str] = []
        for row in rows:
            g = row.get(mapping.group_column, "").strip() if grouped else None
            if grouped and not g:
                continue
            if grouped and g not in group_order:
                group_order.append(g)
            for m in metrics:
                v = _to_float(row.get(m, "").strip())
                buckets.setdefault((g, m), []).append(
                    1.0 if mapping.aggregation == "count" else v
                )

        def axis_values(g: str | None) -> list[dict]:
            return [{"x": m, "y": self._agg(buckets.get((g, m), []), mapping.aggregation)}
                    for m in metrics]

        if grouped:
            return [{"group": g, "values": axis_values(g)} for g in group_order]
        return axis_values(None)

    def _bin_edges(self, values: list[float]) -> list[float]:
        """Equal-width bin edges. Bin count is the larger of Freedman-Diaconis and
        Sturges (FD under-bins multimodal data; Sturges keeps a sensible floor),
        clamped to [5, 60]."""
        n = len(values)
        vmin, vmax = min(values), max(values)
        if vmax <= vmin:
            return [vmin, vmin + 1]
        sorted_v = sorted(values)
        iqr = self._quantile(sorted_v, 0.75) - self._quantile(sorted_v, 0.25)
        if iqr > 0:
            width = 2 * iqr / (n ** (1 / 3))
            fd = math.ceil((vmax - vmin) / width) if width > 0 else 0
        else:
            fd = math.ceil(math.sqrt(n))
        sturges = math.ceil(math.log2(n) + 1) if n > 1 else 1
        nbins = max(fd, sturges) or 10
        nbins = max(5, min(60, nbins))
        return [vmin + (vmax - vmin) * i / nbins for i in range(nbins + 1)]

    def _transform_histogram(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """Bin the numeric x_column and count rows per bin. y_column/aggregation are
        ignored — the value is always the frequency. Optional group_column produces
        one series per group over shared bin edges (overlaid in the template)."""
        grouped = bool(mapping.group_column)
        entries: list[tuple[float, str | None]] = []
        group_order: list[str] = []
        for row in rows:
            raw_x = row.get(mapping.x_column, "").strip()
            if not raw_x or not _in_range(raw_x, mapping.x_min, mapping.x_max):
                continue
            v = _to_float(raw_x)
            if v is None:
                continue
            g = row.get(mapping.group_column, "").strip() if grouped else None
            if grouped and not g:
                continue
            if grouped and g not in group_order:
                group_order.append(g)
            entries.append((v, g))

        if not entries:
            return []

        edges = self._bin_edges([v for v, _ in entries])
        nb = len(edges) - 1
        binw = (edges[-1] - edges[0]) / nb
        def idx(v: float) -> int:
            i = int((v - edges[0]) / binw) if binw > 0 else 0
            return max(0, min(nb - 1, i))

        def bins_for(counts: list[int]) -> list[dict]:
            return [{"x0": edges[i], "x1": edges[i + 1], "count": counts[i]} for i in range(nb)]

        if grouped:
            counts: dict[str, list[int]] = {g: [0] * nb for g in group_order}
            for v, g in entries:
                counts[g][idx(v)] += 1
            return [{"group": g, "values": bins_for(counts[g])} for g in group_order]

        flat = [0] * nb
        for v, _ in entries:
            flat[idx(v)] += 1
        return bins_for(flat)

    def _transform_violin(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """One violin per x category (optionally per group): a KDE curve plus the
        five-number summary so the template can draw the density and an inner box.

        Density is sampled over a shared y-range so violins align on the y-axis.
        """
        grouped = bool(mapping.group_column)
        buckets: dict[tuple[str, str | None], list[float]] = {}
        x_order: list[str] = []
        group_order: list[str] = []

        for row in rows:
            raw_x = row.get(mapping.x_column, "").strip()
            if not raw_x or not _in_range(raw_x, mapping.x_min, mapping.x_max):
                continue
            x = self._x_key(raw_x, mapping.time_unit) or raw_x
            g = row.get(mapping.group_column, "").strip() if grouped else None
            if grouped and not g:
                continue
            y = _to_float(row.get(mapping.y_column, "").strip())
            if y is None:
                continue
            key = (x, g)
            if key not in buckets:
                buckets[key] = []
                if x not in x_order:
                    x_order.append(x)
                if g and g not in group_order:
                    group_order.append(g)
            buckets[key].append(y)

        all_vals = [v for vals in buckets.values() for v in vals]
        if not all_vals:
            return []
        y_lo, y_hi = min(all_vals), max(all_vals)
        span = y_hi - y_lo or 1.0
        # Pad the sampled range slightly so the density tails aren't clipped.
        y_lo -= span * 0.05
        y_hi += span * 0.05
        N = 48
        sample_ys = [y_lo + (y_hi - y_lo) * i / (N - 1) for i in range(N)]

        result = []
        for (x, g), values in buckets.items():
            stats = self._box_stats(values)
            if stats is None:
                continue
            density = self._kde(values, sample_ys, stats["q1"], stats["q3"])
            entry = {
                "x": x,
                "density": [[sy, d] for sy, d in zip(sample_ys, density)],
                **stats,
            }
            if grouped:
                entry["group"] = g
            result.append(entry)

        result.sort(key=lambda e: (
            x_order.index(e["x"]),
            group_order.index(e["group"]) if grouped else 0,
        ))
        return result

    def _transform_network(self, rows: list[dict], mapping: AxisMapping) -> dict:
        """Aggregate edges by (source, target) and return {nodes, links}."""
        buckets: dict[tuple[str, str], list[float | None]] = {}
        node_seen: list[str] = []
        # Which side of the graph each node came from, so the template can color
        # the two categorical entities distinctly (source vs target). A node seen
        # on both sides is tagged "both".
        node_side: dict[str, str] = {}
        src_label = mapping.x_label or mapping.x_column
        tgt_label = mapping.y_label or mapping.y_column

        for row in rows:
            src = row.get(mapping.x_column, "").strip()
            tgt = row.get(mapping.y_column, "").strip()
            if not src or not tgt:
                continue
            for n in (src, tgt):
                if n not in node_seen:
                    node_seen.append(n)
            node_side[src] = src_label if node_side.get(src, src_label) == src_label else "both"
            node_side[tgt] = tgt_label if node_side.get(tgt, tgt_label) == tgt_label else "both"
            key = (src, tgt)
            if key not in buckets:
                buckets[key] = []
            if mapping.z_column:
                w = row.get(mapping.z_column, "").strip()
                buckets[key].append(_to_float(w) if w else None)
            else:
                buckets[key].append(1.0)

        # Edge weight. For a WEIGHTED graph (z_column set) the buckets preserve row
        # order, so collapse each edge's measure to one grain-correct representative
        # — this prevents a repeated/cumulative column (e.g. season 'wins') from
        # being multiplied by the number of underlying rows. For an UNWEIGHTED graph
        # the weight is just the number of connecting rows.
        def _edge_weight(vals: list[float | None]) -> float | None:
            if mapping.z_column:
                return self._collapse_measure(vals, mapping.aggregation)
            return self._agg(vals, "sum")

        edge_weight = {(src, tgt): _edge_weight(vals) for (src, tgt), vals in buckets.items()}
        links = [
            {"source": src, "target": tgt, "weight": w}
            for (src, tgt), w in edge_weight.items()
        ]

        # Node size from its collapsed edge weights. If every neighbour carries the
        # SAME value it's an attribute of THIS node (e.g. a constructor's own season
        # wins repeated across its drivers) → take it once, don't sum. Otherwise sum
        # each neighbour's distinct contribution (e.g. each driver's own wins).
        if mapping.z_column:
            incident: dict[str, list[float]] = {}
            for (src, tgt), w in edge_weight.items():
                if w is None:
                    continue
                incident.setdefault(src, []).append(w)
                incident.setdefault(tgt, []).append(w)

            def _node_size(reps: list[float]) -> float:
                if not reps:
                    return 0.0
                return reps[0] if len(set(reps)) == 1 else sum(reps)

            node_list = [
                {"id": n, "group": node_side.get(n, ""), "size": _node_size(incident.get(n, []))}
                for n in node_seen
            ]
        else:
            node_list = [{"id": n, "group": node_side.get(n, "")} for n in node_seen]

        # Cap huge graphs to their most-connected core so they render legibly
        # (an unbounded force layout of thousands of nodes reads as a black blob).
        MAX_NODES = 120
        if len(node_list) > MAX_NODES:
            degree: dict[str, int] = {}
            for src, tgt in buckets:
                degree[src] = degree.get(src, 0) + 1
                degree[tgt] = degree.get(tgt, 0) + 1
            keep = set(sorted(degree, key=lambda n: degree[n], reverse=True)[:MAX_NODES])
            node_list = [n for n in node_list if n["id"] in keep]
            links = [l for l in links if l["source"] in keep and l["target"] in keep]

        # Annotate each node with its degree (number of incident edges) so a
        # "minimum connections" threshold can filter on graph topology — there's no
        # column for it. Computed from the FINAL links, after any capping.
        deg: dict[str, int] = {}
        for l in links:
            deg[l["source"]] = deg.get(l["source"], 0) + 1
            deg[l["target"]] = deg.get(l["target"], 0) + 1
        for n in node_list:
            n["degree"] = deg.get(n["id"], 0)

        return {"nodes": node_list, "links": links}

    @staticmethod
    def _column_is_numeric(rows: list[dict], col: str, sample: int = 50) -> bool:
        """True if a sample of the column's non-empty values all parse as floats."""
        seen = 0
        for row in rows:
            v = row.get(col, "").strip()
            if not v:
                continue
            if _to_float(v) is None:
                return False
            seen += 1
            if seen >= sample:
                break
        return seen > 0

    def _transform_heatmap_density(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """2D histogram: bin two numeric axes into a grid and count/aggregate per
        cell. Output cells as {x0, x1, y0, y1, z}."""
        xs: list[float] = []
        ys: list[float] = []
        zs: list[float | None] = []
        for row in rows:
            rx = row.get(mapping.x_column, "").strip()
            ry = row.get(mapping.y_column, "").strip()
            if not _in_range(rx, mapping.x_min, mapping.x_max):
                continue
            vx, vy = _to_float(rx), _to_float(ry)
            if vx is None or vy is None:
                continue
            z = _to_float(row.get(mapping.z_column, "").strip()) if mapping.z_column else None
            xs.append(vx)
            ys.append(vy)
            zs.append(z)

        if not xs:
            return []

        xe = self._bin_edges(xs)
        ye = self._bin_edges(ys)
        nbx, nby = len(xe) - 1, len(ye) - 1
        bwx = (xe[-1] - xe[0]) / nbx
        bwy = (ye[-1] - ye[0]) / nby

        def idx(v: float, e0: float, bw: float, nb: int) -> int:
            i = int((v - e0) / bw) if bw > 0 else 0
            return max(0, min(nb - 1, i))

        buckets: dict[tuple[int, int], list[float | None]] = {}
        for vx, vy, z in zip(xs, ys, zs):
            key = (idx(vx, xe[0], bwx, nbx), idx(vy, ye[0], bwy, nby))
            buckets.setdefault(key, []).append(1.0 if not mapping.z_column else z)

        agg = mapping.aggregation if mapping.z_column else "sum"
        return [
            {"x0": xe[ix], "x1": xe[ix + 1], "y0": ye[iy], "y1": ye[iy + 1],
             "z": self._agg(vals, agg)}
            for (ix, iy), vals in buckets.items()
        ]

    def _transform_heatmap(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """Matrix heatmap: one {x, y, z} cell per unique (x_column, y_column) pair.
        When both axes are numeric, produce a binned density heatmap instead."""
        if (self._column_is_numeric(rows, mapping.x_column)
                and self._column_is_numeric(rows, mapping.y_column)):
            return self._transform_heatmap_density(rows, mapping)

        buckets: dict[tuple[str, str], list[float | None]] = {}
        x_seen: list[str] = []
        y_seen: list[str] = []

        for row in rows:
            raw_x = row.get(mapping.x_column, "").strip()
            y_cat = row.get(mapping.y_column, "").strip()
            if not raw_x or not y_cat:
                continue
            if not _in_range(raw_x, mapping.x_min, mapping.x_max):
                continue
            x = self._x_key(raw_x, mapping.time_unit) or raw_x
            key = (x, y_cat)
            if key not in buckets:
                buckets[key] = []
                if x not in x_seen:
                    x_seen.append(x)
                if y_cat not in y_seen:
                    y_seen.append(y_cat)
            if mapping.z_column:
                z_str = row.get(mapping.z_column, "").strip()
                buckets[key].append(_to_float(z_str) if z_str else None)
            else:
                buckets[key].append(1.0)

        agg = mapping.aggregation if mapping.z_column else "sum"
        return [
            {"x": x, "y": y, "z": self._agg(buckets[(x, y)], agg)}
            for x in x_seen
            for y in y_seen
            if (x, y) in buckets
        ]

    def _transform_map(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """Output one point per row for symbol maps — no aggregation."""
        result = []
        for row in rows:
            lon_str = row.get(mapping.x_column, "").strip()
            lat_str = row.get(mapping.y_column, "").strip()
            if not lon_str or not lat_str:
                continue
            lon = _to_float(lon_str)
            lat = _to_float(lat_str)
            if lon is None or lat is None:
                continue
            point: dict = {"x": lon, "y": lat}
            if mapping.z_column:
                z_str = row.get(mapping.z_column, "").strip()
                point["z"] = _to_float(z_str) if z_str else None
            if mapping.label_column:
                point["label"] = row.get(mapping.label_column, "").strip()
            if mapping.group_column:
                point["group"] = row.get(mapping.group_column, "").strip()
            result.append(point)
        return result

    def _transform_labeled(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """Output one point per unique label — no cross-row aggregation."""
        result = []
        for row in rows:
            raw_x = row.get(mapping.x_column, "").strip()
            y_str = row.get(mapping.y_column, "").strip()
            label = row.get(mapping.label_column, "").strip()
            if not _in_range(raw_x, mapping.x_min, mapping.x_max):
                continue
            x = self._x_key(raw_x, mapping.time_unit)
            if not x or not label:
                continue
            try:
                x_val = float(x)
            except (ValueError, TypeError):
                x_val = x
            point: dict = {"x": x_val, "y": _to_float(y_str) if y_str else None, "label": label}
            if mapping.z_column:
                z_str = row.get(mapping.z_column, "").strip()
                point["z"] = _to_float(z_str) if z_str else None
            result.append(point)
        return result

    def _transform_flat(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        allowed = set(mapping.group_filter) if mapping.group_filter else None
        buckets: dict[str, list[float | None]] = {}
        z_buckets: dict[str, list[float | None]] = {}
        order: list[str] = []

        for row in rows:
            raw_x = row.get(mapping.x_column, "").strip()
            y = row.get(mapping.y_column, "").strip()
            if not _in_range(raw_x, mapping.x_min, mapping.x_max):
                continue
            x = self._x_key(raw_x, mapping.time_unit)
            if x and (allowed is None or x in allowed):
                if x not in buckets:
                    buckets[x] = []
                    z_buckets[x] = []
                    order.append(x)
                buckets[x].append(1.0 if mapping.aggregation == "count" else (_to_float(y) if y else None))
                if mapping.z_column:
                    z = row.get(mapping.z_column, "").strip()
                    z_buckets[x].append(_to_float(z) if z else None)

        result = [{"x": x, "y": self._agg(buckets[x], mapping.aggregation)} for x in order]
        if mapping.z_column:
            for i, x in enumerate(order):
                result[i]["z"] = self._agg(z_buckets[x], mapping.aggregation)
        if mapping.top_n:
            result = sorted(result, key=lambda d: (d["y"] is None, d["y"] or 0), reverse=True)[: mapping.top_n]
        return self._sort(result, mapping.sort_order)

    def _transform_grouped(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        allowed = set(mapping.group_filter) if mapping.group_filter else None
        # buckets[group][x] = list of y values
        buckets: dict[str, dict[str, list[float | None]]] = {}
        x_order: dict[str, list[str]] = {}

        z_buckets: dict[str, dict[str, list[float | None]]] = {}

        for row in rows:
            raw_x = row.get(mapping.x_column,    "").strip()
            y     = row.get(mapping.y_column,     "").strip()
            group = row.get(mapping.group_column, "").strip()
            if not _in_range(raw_x, mapping.x_min, mapping.x_max):
                continue
            x = self._x_key(raw_x, mapping.time_unit)
            if x and group and (allowed is None or group in allowed):
                if group not in buckets:
                    buckets[group] = {}
                    z_buckets[group] = {}
                    x_order[group] = []
                if x not in buckets[group]:
                    buckets[group][x] = []
                    z_buckets[group][x] = []
                    x_order[group].append(x)
                buckets[group][x].append(1.0 if mapping.aggregation == "count" else (_to_float(y) if y else None))
                if mapping.z_column:
                    z = row.get(mapping.z_column, "").strip()
                    z_buckets[group][x].append(_to_float(z) if z else None)

        # Aggregate y (and optional z) values per (group, x)
        result = []
        for group in sorted(buckets):
            values = [
                {"x": x, "y": self._agg(buckets[group][x], mapping.aggregation)}
                for x in x_order[group]
            ]
            if mapping.z_column:
                for i, x in enumerate(x_order[group]):
                    values[i]["z"] = self._agg(z_buckets[group][x], mapping.aggregation)
            result.append({"group": group, "values": values})

        # top_n: rank groups by sum of their aggregated y, keep the N highest
        if mapping.top_n and len(result) > mapping.top_n:
            def _total(g: dict) -> float:
                return sum(v["y"] for v in g["values"] if v["y"] is not None)
            result = sorted(result, key=_total, reverse=True)[: mapping.top_n]

        # Sort x categories by their total y across all groups
        if mapping.sort_order in ("asc", "desc"):
            cat_totals: dict[str, float] = {}
            for grp in result:
                for pt in grp["values"]:
                    cat_totals[pt["x"]] = cat_totals.get(pt["x"], 0) + (pt["y"] or 0)
            reverse = mapping.sort_order == "desc"
            sorted_cats = sorted(cat_totals, key=lambda x: cat_totals[x], reverse=reverse)
            rank = {x: i for i, x in enumerate(sorted_cats)}
            for grp in result:
                grp["values"].sort(key=lambda pt: rank.get(pt["x"], 0))

        return result

    @staticmethod
    def _natural_sorted(vals) -> list[str]:
        """Sort period labels left→right: numerically if all numeric, chronologically
        if all dates, else lexically."""
        vals = list(vals)
        nums = {v: _to_float(v) for v in vals}
        if vals and all(n is not None for n in nums.values()):
            return sorted(vals, key=lambda v: nums[v])
        dts = {v: _parse_dt(v) for v in vals}
        if vals and all(d is not None for d in dts.values()):
            return sorted(vals, key=lambda v: dts[v])
        return sorted(vals)

    def _transform_bump(self, rows: list[dict], mapping: AxisMapping) -> list[dict]:
        """Rankings over an ordered period. Aggregate the measure per (group, x) —
        exactly the grouped-series shape — then, at each x, RANK the groups (rank 1 =
        highest value by default) and attach that rank to each point. The template
        plots rank on the y-axis (1 on top) so each series bumps up and down over x."""
        grouped = self._transform_grouped(rows, mapping)   # [{group, values:[{x, y}]}]
        x_order = self._natural_sorted({pt["x"] for g in grouped for pt in g["values"]})
        pos = {x: i for i, x in enumerate(x_order)}

        # The highest measure is rank 1 (top performer on top) — the standard bump
        # convention. (sort_order drives the grouped x-ordering, not the ranking.)
        for x in x_order:
            present = []
            for g in grouped:
                y = next((p["y"] for p in g["values"] if p["x"] == x), None)
                if y is not None:
                    present.append((g["group"], y))
            present.sort(key=lambda gy: gy[1], reverse=True)
            rank_of = {grp: i + 1 for i, (grp, _) in enumerate(present)}
            for g in grouped:
                for p in g["values"]:
                    if p["x"] == x and g["group"] in rank_of:
                        p["rank"] = rank_of[g["group"]]

        # Keep only ranked points, ordered left→right; drop any now-empty series.
        result = []
        for g in grouped:
            vals = [p for p in sorted(g["values"], key=lambda p: pos.get(p["x"], 0))
                    if "rank" in p]
            if vals:
                result.append({"group": g["group"], "values": vals})
        return result
