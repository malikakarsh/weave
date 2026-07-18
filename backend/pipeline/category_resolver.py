"""Deterministic resolution of user-referenced category values against the data.

The LLM only sees a few sample values per column, so at high cardinality it can
hallucinate a category name or miss the exact one. This resolver is the ground
truth: it matches a referenced term (e.g. "good") against the ACTUAL distinct
values of the relevant column and decides:

  exact (case-insensitive) → apply                          (no user input)
  unique fuzzy match        → auto-correct and apply         (no user input)
  >= 2 fuzzy matches        → ambiguous  → ask the user
  0 matches                 → not found  → ask with closest options

It rewrites resolved references in-place on the mapping and collects any
ambiguities as `Clarification`s for a human-in-the-loop step.
"""

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from models import AxisMapping


def _norm(s: str) -> str:
    return s.strip().lower()


def _rank(term: str, values: list[str]) -> list[str]:
    """Values sorted by string similarity to the term (most similar first)."""
    t = _norm(term)
    return sorted(values, key=lambda v: SequenceMatcher(None, t, _norm(v)).ratio(), reverse=True)


def distinct_values(rows: list[dict], column: str) -> list[str]:
    """Distinct non-empty values of a column, in first-seen order."""
    seen: list[str] = []
    known: set[str] = set()
    for row in rows:
        v = row.get(column, "").strip()
        if v and v not in known:
            known.add(v)
            seen.append(v)
    return seen


# Never suggest more than this — on a high-cardinality column, show the closest
# few and let the user decide rather than dumping dozens of near-identical names.
MAX_OPTIONS = 5
# Minimum string-similarity for a value to be worth suggesting when nothing
# matches structurally (keeps unrelated values out of the "did you mean" list).
MIN_SIMILARITY = 0.35


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def resolve_term(term: str, values: list[str]) -> tuple[str, object]:
    """Return (kind, result):
      ("exact", value) | ("unique", value) | ("ambiguous", [<=5 closest]) | ("none", [<=5 closest])

    Only exact and a single clean structural match resolve automatically. Anything
    fuzzier is surfaced to the user as the top-N closest candidates by similarity.
    """
    t = _norm(term)
    by_norm = {}
    for v in values:
        by_norm.setdefault(_norm(v), v)

    if t in by_norm:
        return ("exact", by_norm[t])

    # Structural candidates: substring (either direction, term length >= 2) or a
    # shared whitespace token. These are "the term clearly refers to this value".
    def structural(v: str) -> bool:
        nv = _norm(v)
        if len(t) >= 2 and (t in nv or nv in t):
            return True
        return bool(set(t.split()) & set(nv.split()))

    cands = _rank(t, [v for v in values if structural(v)])
    if len(cands) == 1:
        return ("unique", cands[0])
    if len(cands) >= 2:
        return ("ambiguous", cands[:MAX_OPTIONS])   # top-N closest, not all of them

    # No structural match — offer the closest by similarity, above a floor so we
    # don't suggest unrelated values. Fall back to the raw closest if none pass.
    ranked = _rank(t, values)
    close = [v for v in ranked if _ratio(t, _norm(v)) >= MIN_SIMILARITY]
    return ("none", (close or ranked)[:MAX_OPTIONS])


@dataclass
class Clarification:
    field: str            # "category_colors" | "filters" | "group_filter"
    term: str             # what the user referenced
    column: str           # which column it belongs to
    options: list[str]    # candidate values to choose from
    reason: str           # "ambiguous" | "none"
    color: str | None = None   # for category_colors: the color to apply once resolved


@dataclass
class ResolveResult:
    mapping: AxisMapping                 # with confidently-resolved references applied
    clarifications: list[Clarification] = field(default_factory=list)


def resolve_references(mapping: AxisMapping, rows: list[dict]) -> ResolveResult:
    """Resolve every user-referenced category value in the mapping against the
    data. Exact/unique matches are rewritten on the mapping; ambiguous/not-found
    references become Clarifications for the caller to surface."""
    clarifications: list[Clarification] = []
    updates: dict = {}
    _cache: dict[str, list[str]] = {}

    def vals(col: str) -> list[str]:
        if col not in _cache:
            _cache[col] = distinct_values(rows, col)
        return _cache[col]

    # ── category_colors: keys are values of the colored dimension ──
    color_col = mapping.group_column or mapping.x_column
    if mapping.category_colors and color_col:
        resolved: dict[str, str] = {}
        for term, color in mapping.category_colors.items():
            kind, res = resolve_term(term, vals(color_col))
            if kind in ("exact", "unique"):
                resolved[res] = color
            else:
                clarifications.append(Clarification(
                    field="category_colors", term=term, column=color_col,
                    options=list(res), reason=kind, color=color))
        updates["category_colors"] = resolved or None

    # ── filters: each has an explicit column and a list of values ──
    if mapping.filters:
        new_filters = []
        for f in mapping.filters:
            # Threshold filters (min/max, no values) need no category resolution.
            if not f.values:
                new_filters.append(f)
                continue
            kept = []
            for term in f.values:
                kind, res = resolve_term(term, vals(f.column))
                if kind in ("exact", "unique"):
                    kept.append(res)
                else:
                    clarifications.append(Clarification(
                        field="filters", term=term, column=f.column,
                        options=list(res), reason=kind))
            new_filters.append(f.model_copy(update={"values": kept}))
        updates["filters"] = new_filters

    # ── group_filter: values of the group_column ──
    if mapping.group_filter and mapping.group_column:
        kept = []
        for term in mapping.group_filter:
            kind, res = resolve_term(term, vals(mapping.group_column))
            if kind in ("exact", "unique"):
                kept.append(res)
            else:
                clarifications.append(Clarification(
                    field="group_filter", term=term, column=mapping.group_column,
                    options=list(res), reason=kind))
        updates["group_filter"] = kept or None

    return ResolveResult(mapping.model_copy(update=updates), clarifications)


def apply_choice(mapping: AxisMapping, clar: Clarification, chosen: str) -> AxisMapping:
    """Add a user-chosen category value back into the mapping field it belongs to."""
    if clar.field == "category_colors":
        cc = dict(mapping.category_colors or {})
        cc[chosen] = clar.color
        return mapping.model_copy(update={"category_colors": cc})
    if clar.field == "group_filter":
        return mapping.model_copy(update={"group_filter": list(mapping.group_filter or []) + [chosen]})
    if clar.field == "filters":
        filters = []
        added = False
        for f in (mapping.filters or []):
            if f.column == clar.column:
                f = f.model_copy(update={"values": list(f.values) + [chosen]})
                added = True
            filters.append(f)
        if not added:
            from models.spec import FilterSpec
            filters.append(FilterSpec(column=clar.column, values=[chosen]))
        return mapping.model_copy(update={"filters": filters})
    return mapping


class ClarificationNeeded(Exception):
    """Raised through the pipeline when a category reference is ambiguous/unknown."""
    def __init__(self, mapping: AxisMapping, clarifications: list[Clarification]):
        self.mapping = mapping
        self.clarifications = clarifications
        super().__init__("clarification needed")
