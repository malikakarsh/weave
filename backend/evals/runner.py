"""
UAT eval runner for the Weave pipeline.

Usage:
  python -m evals.runner              # run all cases
  python -m evals.runner time_unit    # run cases whose name contains 'time_unit'
  python -m evals.runner --fast       # skip LLM; only run transformer checks
"""

import sys
import time
from pathlib import Path

# Allow running from backend/
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from evals.cases import CASES
from pipeline.data_loader import DataLoader
from pipeline.llm_mapper import LLMMapper
from pipeline.transformer import Transformer

# ── Terminal colours ───────────────────────────────────────────────────────────
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

PASS = f"{GREEN}PASS{RESET}"
FAIL = f"{RED}FAIL{RESET}"
SKIP = f"{YELLOW}SKIP{RESET}"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _flat_xs(data: list[dict]) -> set:
    """Return all x values from flat or grouped data."""
    if data and "group" in data[0]:
        return {pt["x"] for grp in data for pt in grp["values"]}
    return {d["x"] for d in data}


def _flat_points(data: list[dict]) -> list[dict]:
    """Return all {x, y} points regardless of grouped/flat shape."""
    if data and "group" in data[0]:
        return [pt for grp in data for pt in grp["values"]]
    return data


def _check_mapping(mapping, expect: dict) -> list[str]:
    """Return list of failure messages (empty = all passed)."""
    failures = []
    for field, expected in expect.items():
        actual = getattr(mapping, field, "MISSING")
        if actual == "MISSING":
            failures.append(f"  mapping.{field} not found on AxisMapping")
            continue
        # For list fields, order-insensitive comparison
        if isinstance(expected, list) and isinstance(actual, list):
            if sorted(str(x) for x in expected) != sorted(str(x) for x in actual):
                failures.append(f"  mapping.{field}: expected {expected!r}, got {actual!r}")
        elif actual != expected:
            failures.append(f"  mapping.{field}: expected {expected!r}, got {actual!r}")
    return failures


def _check_data(data, expect: dict) -> list[str]:
    failures = []

    # Network graph shape: {nodes: [...], links: [...]}
    if isinstance(data, dict) and "nodes" in data:
        if "nodes_count" in expect:
            nc = len(data["nodes"])
            if nc != expect["nodes_count"]:
                failures.append(f"  nodes count: expected {expect['nodes_count']}, got {nc}")
        if "links_count" in expect:
            lc = len(data["links"])
            if lc != expect["links_count"]:
                failures.append(f"  links count: expected {expect['links_count']}, got {lc}")
        if "node_ids" in expect:
            ids = {n["id"] for n in data["nodes"]}
            for nid in expect["node_ids"]:
                if nid not in ids:
                    failures.append(f"  node_ids: '{nid}' not found in nodes")
        return failures

    is_grouped = bool(data) and "group" in data[0]

    if "grouped" in expect:
        if is_grouped != expect["grouped"]:
            shape = "grouped" if is_grouped else "flat"
            exp_shape = "grouped" if expect["grouped"] else "flat"
            failures.append(f"  data shape: expected {exp_shape}, got {shape}")

    if "count" in expect:
        if len(data) != expect["count"]:
            failures.append(f"  data length: expected {expect['count']}, got {len(data)}")

    if "values_count" in expect and is_grouped:
        vc = expect["values_count"]
        for grp in data:
            if len(grp["values"]) != vc:
                failures.append(
                    f"  group '{grp['group']}' values: expected {vc}, got {len(grp['values'])}"
                )

    xs = _flat_xs(data)

    if "x_includes" in expect:
        for x in expect["x_includes"]:
            if x not in xs:
                failures.append(f"  x_includes: '{x}' not found in data")

    if "x_excludes" in expect:
        for x in expect["x_excludes"]:
            if x in xs:
                failures.append(f"  x_excludes: '{x}' found in data (should be absent)")

    if "spot" in expect:
        points = _flat_points(data)
        for check in expect["spot"]:
            found = any(
                p["x"] == check["x"] and abs((p["y"] or 0) - check["y"]) < 0.01
                for p in points
            )
            if not found:
                failures.append(f"  spot check failed: {check} not found in data")

    return failures


# ── Runner ─────────────────────────────────────────────────────────────────────

def run_cases(cases: list[dict], fast: bool = False) -> None:
    passed = failed = skipped = 0
    loader    = DataLoader()
    mapper    = LLMMapper()
    transformer = Transformer()

    for case in cases:
        name = case["name"]
        print(f"\n{BOLD}{CYAN}▸ {name}{RESET}")

        # Load CSV
        try:
            schema, rows = loader.load(case["csv"])
        except Exception as e:
            print(f"  {FAIL}  CSV load error: {e}")
            failed += 1
            continue

        mapping = None
        map_failures = []

        if fast:
            print(f"  {SKIP}  LLM mapping (--fast mode)")
            skipped += 1
        else:
            # LLM mapping
            t0 = time.time()
            try:
                mapping = mapper.map(schema, case["prompt"])
                elapsed = time.time() - t0
                facet_info = ""
                if mapping.facet_direction:
                    facet_info = f" facet={mapping.facet_direction!r} free_y={mapping.facet_free_y!r}"
                print(f"  {DIM}mapped in {elapsed:.1f}s  →  "
                      f"chart={mapping.chart_type!r} x={mapping.x_column!r} "
                      f"y={mapping.y_column!r} z={mapping.z_column!r} "
                      f"group={mapping.group_column!r} agg={mapping.aggregation!r} "
                      f"top_n={mapping.top_n!r} sort={mapping.sort_order!r} "
                      f"time_unit={mapping.time_unit!r} "
                      f"x_min={mapping.x_min!r} x_max={mapping.x_max!r}"
                      f"{facet_info}{RESET}")
            except Exception as e:
                print(f"  {FAIL}  LLM error: {e}")
                failed += 1
                continue

            if "expect_mapping" in case:
                map_failures = _check_mapping(mapping, case["expect_mapping"])
                if map_failures:
                    for f in map_failures:
                        print(f"{RED}{f}{RESET}")

        # Transformer
        data_failures = []
        if mapping is not None and "expect_data" in case:
            try:
                data = transformer.transform(rows, mapping)
                data_failures = _check_data(data, case["expect_data"])
                if data_failures:
                    for f in data_failures:
                        print(f"{RED}{f}{RESET}")
            except Exception as e:
                data_failures.append(f"  transformer error: {e}")
                print(f"{RED}  transformer error: {e}{RESET}")

        all_failures = map_failures + data_failures
        if fast:
            pass  # already counted as skipped
        elif all_failures:
            print(f"  {FAIL}  {len(all_failures)} assertion(s) failed")
            failed += 1
        else:
            print(f"  {PASS}")
            passed += 1

    # Summary
    total = passed + failed + skipped
    print(f"\n{'─'*50}")
    print(f"{BOLD}Results: {total} cases  "
          f"{GREEN}{passed} passed{RESET}  "
          f"{RED}{failed} failed{RESET}  "
          f"{YELLOW}{skipped} skipped{RESET}{RESET}")
    if failed:
        sys.exit(1)


def main():
    args = sys.argv[1:]
    fast = "--fast" in args
    filters = [a for a in args if not a.startswith("--")]

    cases = CASES
    if filters:
        keyword = " ".join(filters).lower()
        cases = [c for c in CASES if keyword in c["name"].lower()]
        if not cases:
            print(f"{YELLOW}No cases matched {keyword!r}{RESET}")
            sys.exit(0)
        print(f"{DIM}Running {len(cases)} case(s) matching {keyword!r}{RESET}")

    run_cases(cases, fast=fast)


if __name__ == "__main__":
    main()
