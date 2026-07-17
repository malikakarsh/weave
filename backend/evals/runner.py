"""
UAT eval runner for the Weave pipeline.

Usage:
  python -m evals.runner                                  # run all cases (sequential, with latency)
  python -m evals.runner time_unit                        # filter by name
  python -m evals.runner --batch                          # submit all cases as one batch (cheaper)
  python -m evals.runner --fast                           # skip LLM calls
  python -m evals.runner --provider ollama --model llama3.2
  python -m evals.runner --provider anthropic --model claude-haiku-4-5
"""

import sys
import time
from pathlib import Path

# Allow running from backend/
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from evals.cases import CASES
from models import AxisMapping
from pipeline.data_loader import DataLoader
from pipeline.llm_mapper import LLMMapper
from pipeline.providers import get_provider
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

def _is_grouped(data: list[dict]) -> bool:
    """True only for the {group, values} grouped format (not symbol_map flat points)."""
    return bool(data) and "group" in data[0] and "values" in data[0]


def _flat_xs(data: list[dict]) -> set:
    """Return all x values from flat or grouped data."""
    if _is_grouped(data):
        return {pt["x"] for grp in data for pt in grp["values"]}
    return {d["x"] for d in data}


def _flat_points(data: list[dict]) -> list[dict]:
    """Return all {x, y} points regardless of grouped/flat shape."""
    if _is_grouped(data):
        return [pt for grp in data for pt in grp["values"]]
    return data


def _plain(x):
    """Normalise pydantic sub-models (LimitSpec/FilterSpec) to plain data."""
    if hasattr(x, "model_dump"):
        return x.model_dump()
    if isinstance(x, list):
        return [_plain(i) for i in x]
    return x


def _check_mapping(mapping, expect: dict) -> list[str]:
    """Return list of failure messages (empty = all passed)."""
    failures = []
    for field, expected in expect.items():
        actual = getattr(mapping, field, "MISSING")
        if actual == "MISSING":
            failures.append(f"  mapping.{field} not found on AxisMapping")
            continue
        actual = _plain(actual)
        expected = _plain(expected)
        # Dict fields (e.g. limit): every expected key must match — extra keys OK.
        if isinstance(expected, dict) and isinstance(actual, dict):
            for k, v in expected.items():
                if actual.get(k) != v:
                    failures.append(f"  mapping.{field}.{k}: expected {v!r}, got {actual.get(k)!r}")
        # List fields: order-insensitive comparison
        elif isinstance(expected, list) and isinstance(actual, list):
            if sorted(str(x) for x in expected) != sorted(str(x) for x in actual):
                failures.append(f"  mapping.{field}: expected {expected!r}, got {actual!r}")
        elif actual != expected:
            failures.append(f"  mapping.{field}: expected {expected!r}, got {actual!r}")
    return failures


def _check_mapping_custom(mapping, expect_custom: dict) -> list[str]:
    """Handle assertions that can't be expressed as simple equality."""
    failures = []
    if expect_custom.get("color_is_set"):
        if not mapping.color:
            failures.append("  mapping.color: expected a color value, got None/empty")
    if "category_color_key" in expect_custom:
        key = expect_custom["category_color_key"]
        cc = mapping.category_colors or {}
        if key not in cc:
            failures.append(f"  mapping.category_colors: key {key!r} not found (got {cc})")
    if "mark_scale_lt" in expect_custom:
        ms = mapping.mark_scale
        if ms is None or ms >= expect_custom["mark_scale_lt"]:
            failures.append(f"  mapping.mark_scale: expected < {expect_custom['mark_scale_lt']}, got {ms}")
    if "mark_scale_gt" in expect_custom:
        ms = mapping.mark_scale
        if ms is None or ms <= expect_custom["mark_scale_gt"]:
            failures.append(f"  mapping.mark_scale: expected > {expect_custom['mark_scale_gt']}, got {ms}")
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

    # Histogram bin data: list of {x0, x1, count}
    if expect.get("binned"):
        if not data or not all(isinstance(d, dict) and "x0" in d and "x1" in d and "count" in d for d in data):
            failures.append("  binned: expected each item to have x0/x1/count keys")
        elif "total_count" in expect:
            total = sum(d["count"] for d in data)
            if total != expect["total_count"]:
                failures.append(f"  total_count: expected {expect['total_count']}, got {total}")
        return failures

    is_grouped = _is_grouped(data)

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

def _mapping_detail(mapping, label: str) -> str:
    facet_info = ""
    if mapping.facet_direction:
        facet_info = f" facet={mapping.facet_direction!r} free_y={mapping.facet_free_y!r}"
    return (f"  {DIM}{label}  →  "
            f"chart={mapping.chart_type!r} x={mapping.x_column!r} "
            f"y={mapping.y_column!r} z={mapping.z_column!r} "
            f"group={mapping.group_column!r} agg={mapping.aggregation!r} "
            f"top_n={mapping.top_n!r} sort={mapping.sort_order!r} "
            f"color={mapping.color!r} cat_colors={mapping.category_colors!r} "
            f"time_unit={mapping.time_unit!r} "
            f"x_min={mapping.x_min!r} x_max={mapping.x_max!r}"
            f"{facet_info}{RESET}")


def _report_case(case, mapping, rows, transformer, check_mapping: bool) -> bool:
    """Run mapping + data assertions for one case, print failures, return True if passed."""
    map_failures: list[str] = []
    if check_mapping:
        if "expect_mapping" in case:
            map_failures += _check_mapping(mapping, case["expect_mapping"])
        if "expect_mapping_custom" in case:
            map_failures += _check_mapping_custom(mapping, case["expect_mapping_custom"])
    for f in map_failures:
        print(f"{RED}{f}{RESET}")

    data_failures: list[str] = []
    if mapping is not None and "expect_data" in case:
        try:
            data = transformer.transform(rows, mapping)
            data_failures = _check_data(data, case["expect_data"])
            for f in data_failures:
                print(f"{RED}{f}{RESET}")
        except Exception as e:
            data_failures.append(f"  transformer error: {e}")
            print(f"{RED}  transformer error: {e}{RESET}")

    if map_failures + data_failures:
        print(f"  {FAIL}  {len(map_failures + data_failures)} assertion(s) failed")
        return False
    print(f"  {PASS}")
    return True


def _run_fast(cases, loader, transformer) -> tuple[int, int, int, list[float]]:
    passed = failed = skipped = 0
    for case in cases:
        print(f"\n{BOLD}{CYAN}▸ {case['name']}{RESET}")
        try:
            _, rows = loader.load(case["csv"])
        except Exception as e:
            print(f"  {FAIL}  CSV load error: {e}")
            failed += 1
            continue

        if "refine_from" in case:
            stub = dict(case["refine_from"])
            stub.update({k: v for k, v in case.get("expect_mapping", {}).items() if v is not None})
        else:
            stub = case.get("stub_mapping") or case.get("expect_mapping")
        if not stub:
            print(f"  {SKIP}  no stub_mapping defined (--fast mode)")
            skipped += 1
            continue
        try:
            mapping = AxisMapping(**stub)
        except Exception as e:
            print(f"  {SKIP}  cannot build stub mapping: {e}")
            skipped += 1
            continue
        print(f"  {DIM}fast: using stub mapping{RESET}")
        # Mapping is the expected one in fast mode — only data assertions apply.
        if _report_case(case, mapping, rows, transformer, check_mapping=False):
            passed += 1
        else:
            failed += 1
    return passed, failed, skipped, []


def _run_sequential(cases, loader, transformer, mapper) -> tuple[int, int, int, list[float]]:
    """Run cases one at a time with a single LLM call each, timing every request
    so per-case and aggregate latency can be measured."""
    passed = failed = 0
    latencies: list[float] = []
    for case in cases:
        print(f"\n{BOLD}{CYAN}▸ {case['name']}{RESET}")
        try:
            schema, rows = loader.load(case["csv"])
        except Exception as e:
            print(f"  {FAIL}  CSV load error: {e}")
            failed += 1
            continue

        t0 = time.time()
        try:
            if "refine_from" in case:
                current = AxisMapping(**case["refine_from"])
                mapping = mapper.refine(current, [], case["refine_instruction"])
                label = "refined"
            else:
                mapping = mapper.map(schema, case["prompt"])
                label = "mapped"
        except Exception as e:
            print(f"  {FAIL}  LLM error: {e}")
            failed += 1
            continue
        elapsed = time.time() - t0
        latencies.append(elapsed)

        print(_mapping_detail(mapping, f"{label} in {elapsed:.1f}s"))
        if _report_case(case, mapping, rows, transformer, check_mapping=True):
            passed += 1
        else:
            failed += 1
    return passed, failed, 0, latencies


def _run_batch(cases, loader, transformer, mapper) -> tuple[int, int, int, list[float]]:
    """Build one LLM request per case, submit them all as a single batch, then
    parse each response and run assertions."""
    passed = failed = 0

    # ── Phase 1: load CSVs and build the batch requests ──
    jobs = []  # one entry per case: dict with case, rows, and either a request or an error
    for case in cases:
        entry = {"case": case, "rows": None, "request": None, "error": None,
                 "schema": None, "current": None, "is_refine": "refine_from" in case}
        try:
            schema, rows = loader.load(case["csv"])
            entry["schema"], entry["rows"] = schema, rows
            if entry["is_refine"]:
                current = AxisMapping(**case["refine_from"])
                entry["current"] = current
                entry["request"] = mapper.build_refine_request(current, [], case["refine_instruction"])
            else:
                entry["request"] = mapper.build_map_request(schema, case["prompt"])
        except Exception as e:
            entry["error"] = f"setup error: {e}"
        jobs.append(entry)

    # ── Phase 2: submit everything as one batch ──
    live = [j for j in jobs if j["error"] is None]
    print(f"{DIM}Submitting {len(live)} request(s) as a batch — this may take a while…{RESET}\n")
    t0 = time.time()
    raws = mapper.provider.complete_batch([j["request"] for j in live])
    elapsed = time.time() - t0
    for j, raw in zip(live, raws):
        j["raw"] = raw

    # ── Phase 3: parse each response and run assertions ──
    for j in jobs:
        case = j["case"]
        print(f"\n{BOLD}{CYAN}▸ {case['name']}{RESET}")
        if j["error"]:
            print(f"  {FAIL}  {j['error']}")
            failed += 1
            continue
        raw = j.get("raw", "")
        if not raw:
            print(f"  {FAIL}  LLM error: empty batch response")
            failed += 1
            continue
        try:
            if j["is_refine"]:
                mapping = mapper.parse_refine_response(raw, j["current"])
                label = "refined"
            else:
                mapping = mapper.parse_map_response(raw, j["schema"])
                label = "mapped"
        except Exception as e:
            print(f"  {FAIL}  parse error: {e}")
            failed += 1
            continue
        print(_mapping_detail(mapping, label))
        if _report_case(case, mapping, j["rows"], transformer, check_mapping=True):
            passed += 1
        else:
            failed += 1

    print(f"\n{DIM}Batch completed in {elapsed:.1f}s ({len(live)} requests){RESET}")
    return passed, failed, 0, []


def run_cases(
    cases: list[dict],
    fast: bool = False,
    batch: bool = False,
    provider_name: str | None = None,
    model: str | None = None,
) -> None:
    loader = DataLoader()
    transformer = Transformer()

    if fast:
        passed, failed, skipped, latencies = _run_fast(cases, loader, transformer)
    else:
        provider = get_provider(provider_name, model)
        mapper = LLMMapper(provider)
        mode = "batch" if batch else "sequential"
        print(f"{DIM}Provider: {type(provider).__name__}  Model: {provider.model}  Mode: {mode}{RESET}")
        if batch:
            passed, failed, skipped, latencies = _run_batch(cases, loader, transformer, mapper)
        else:
            passed, failed, skipped, latencies = _run_sequential(cases, loader, transformer, mapper)

    # Summary
    total = passed + failed + skipped
    print(f"\n{'─'*50}")
    print(f"{BOLD}Results: {total} cases  "
          f"{GREEN}{passed} passed{RESET}  "
          f"{RED}{failed} failed{RESET}  "
          f"{YELLOW}{skipped} skipped{RESET}{RESET}")
    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"{DIM}LLM latency — avg: {avg:.1f}s  "
              f"min: {min(latencies):.1f}s  "
              f"max: {max(latencies):.1f}s  "
              f"total: {sum(latencies):.1f}s{RESET}")
    if failed:
        sys.exit(1)


def main():
    args = sys.argv[1:]
    fast = "--fast" in args
    batch = "--batch" in args

    # Extract --provider and --model values
    provider_name = None
    model = None
    clean_args = []
    i = 0
    while i < len(args):
        if args[i] in ("--provider", "--model") and i + 1 < len(args):
            if args[i] == "--provider":
                provider_name = args[i + 1]
            else:
                model = args[i + 1]
            i += 2
        elif args[i].startswith("--"):
            i += 1  # skip flags like --fast
        else:
            clean_args.append(args[i])
            i += 1

    filters = clean_args

    cases = CASES
    if filters:
        keyword = " ".join(filters).lower()
        cases = [c for c in CASES if keyword in c["name"].lower()]
        if not cases:
            print(f"{YELLOW}No cases matched {keyword!r}{RESET}")
            sys.exit(0)
        print(f"{DIM}Running {len(cases)} case(s) matching {keyword!r}{RESET}")

    run_cases(cases, fast=fast, batch=batch, provider_name=provider_name, model=model)


if __name__ == "__main__":
    main()
