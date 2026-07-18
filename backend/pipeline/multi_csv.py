"""Multi-CSV joining: load several CSVs into an in-memory SQLite database,
auto-detect join keys by **value overlap**, and execute a validated join plan to
produce one flat table that drops into the existing single-CSV pipeline.

Value overlap (not column-name matching) is the reliable signal for foreign
keys: it survives the `id` / `user_id` / `order_id` naming ambiguity that trips
up name-based heuristics. A column A in one table references column B in another
when most of A's distinct values appear among B's — and B is roughly unique
(a primary key).
"""

import csv
import io
import re
import sqlite3
from dataclasses import dataclass, field

from pydantic import BaseModel

from pipeline.data_loader import DataLoader


def _safe_table_name(filename: str, taken: set[str]) -> str:
    stem = re.sub(r"\.csv$", "", filename, flags=re.IGNORECASE)
    name = re.sub(r"[^0-9a-zA-Z]+", "_", stem).strip("_").lower() or "table"
    if name[0].isdigit():
        name = "t_" + name
    base, i = name, 2
    while name in taken:
        name = f"{base}_{i}"
        i += 1
    taken.add(name)
    return name


def _q(ident: str) -> str:
    """Quote a SQL identifier (table or column) safely."""
    return '"' + ident.replace('"', '""') + '"'


# A foreign-key-looking column name: ends in Id / _id / Key / Code / Uuid, or is
# literally "id". Used with value overlap so a numeric *measure* (points, number,
# grid) can't spuriously "join" to another table's primary key.
_KEY_SUFFIX = re.compile(r"(_id|id|_key|key|_code|code|_uuid|uuid|_guid|guid)$", re.IGNORECASE)


def _looks_like_fk(name: str) -> bool:
    return name.lower() == "id" or bool(_KEY_SUFFIX.search(name))


def _key_stem(name: str) -> str:
    """The entity a key column refers to, stripped of its key suffix and any
    separators/casing: 'raceId'->'race', 'constructor_id'->'constructor',
    'statusId'->'status', 'id'->''. Used to tell same-entity keys apart so a
    `statusId` never joins to a `raceId` just because their integers overlap."""
    stem = _KEY_SUFFIX.sub("", name)
    return re.sub(r"[^0-9a-z]+", "", stem.lower())


def _singularize(table: str) -> str:
    """Rough singular of a table name for matching a bare `id` PK to a
    `<entity>Id` FK: 'drivers'->'driver', 'races'->'race', 'status'->'status'."""
    t = re.sub(r"[^0-9a-z]+", "", table.lower())
    if t.endswith("ies"):
        return t[:-3] + "y"
    if t.endswith("sses") or t.endswith("us") or t.endswith("ss"):
        return t          # 'status', 'class' — don't strip
    return t[:-1] if t.endswith("s") else t


def _keys_compatible(ca: str, cb: str, table_a: str, table_b: str) -> bool:
    """True if two key columns plausibly reference the SAME entity, by name.
    Either their stems match ('raceId'~'raceId', 'constructor_id'~'constructorId'),
    or one is a bare 'id' primary key whose table matches the other's stem
    ('customers.id' ~ 'orders.customer_id')."""
    sa, sb = _key_stem(ca), _key_stem(cb)
    if sa and sb and sa == sb:
        return True
    # bare "id" PK ↔ "<entity>Id" FK: the id's table name must equal the FK stem
    if sa == "" and sb and _singularize(table_a) == sb:
        return True
    if sb == "" and sa and _singularize(table_b) == sa:
        return True
    return False


@dataclass
class TableInfo:
    name: str                       # safe SQL table name
    source: str                     # original filename
    columns: list[str]              # original column names
    row_count: int
    sample: dict[str, list[str]] = field(default_factory=dict)  # per-column sample values


# ── loading ──────────────────────────────────────────────────────────────────
def load_tables(files: list[tuple[str, str]]) -> tuple[sqlite3.Connection, dict[str, TableInfo]]:
    """Load `(filename, path)` CSVs into an in-memory SQLite DB (all columns TEXT
    — joins are string-equality, and the final flat CSV is re-typed downstream)."""
    conn = sqlite3.connect(":memory:")
    loader = DataLoader()
    tables: dict[str, TableInfo] = {}
    taken: set[str] = set()

    for filename, path in files:
        header, rows = loader.read_rows(path)
        tname = _safe_table_name(filename, taken)
        cols_sql = ", ".join(f"{_q(c)} TEXT" for c in header)
        conn.execute(f"CREATE TABLE {_q(tname)} ({cols_sql})")
        placeholders = ", ".join("?" for _ in header)
        col_list = ", ".join(_q(c) for c in header)
        conn.executemany(
            f"INSERT INTO {_q(tname)} ({col_list}) VALUES ({placeholders})",
            [[row.get(c, "") for c in header] for row in rows],
        )
        info = TableInfo(name=tname, source=filename, columns=header, row_count=len(rows))
        for c in header:
            vals = [r[0] for r in conn.execute(
                f"SELECT {_q(c)} FROM {_q(tname)} WHERE {_q(c)} != '' LIMIT 3"
            ).fetchall()]
            info.sample[c] = vals
        tables[tname] = info

    conn.commit()
    return conn, tables


# ── join detection (value overlap) ───────────────────────────────────────────
@dataclass
class JoinCandidate:
    left_table: str
    left_col: str
    right_table: str
    right_col: str
    overlap: float          # fraction of left's distinct values found in right
    right_uniqueness: float  # how key-like the right column is (distinct/rows)
    left_uniqueness: float   # how unique the FK side is (1.0 → a 1:1 lookup)
    confidence: float
    # Additional (left_col, right_col) pairs for a COMPOSITE join. Empty for a
    # normal single-column join; e.g. [("driverId", "driverId")] on top of the
    # primary ("raceId", "raceId") makes results ⋈ driver_standings a 1:1 match.
    extra_pairs: list = field(default_factory=list)

    @property
    def all_pairs(self) -> list[tuple[str, str]]:
        return [(self.left_col, self.right_col), *self.extra_pairs]


def _distinct_values(conn, table, col, limit) -> set[str]:
    return {
        r[0] for r in conn.execute(
            f"SELECT DISTINCT {_q(col)} FROM {_q(table)} WHERE {_q(col)} != '' LIMIT {int(limit)}"
        ).fetchall()
    }


def _is_numeric_col(conn, table, col, sample: int = 50) -> bool:
    """True if a sample of non-empty values all parse as numbers — used to tell a
    numeric MEASURE (points, wins) from a string dimension (country) that share a
    name across tables."""
    vals = [r[0] for r in conn.execute(
        f"SELECT {_q(col)} FROM {_q(table)} WHERE {_q(col)} != '' LIMIT {int(sample)}"
    ).fetchall()]
    if not vals:
        return False
    for v in vals:
        try:
            float(str(v).replace(",", ""))
        except ValueError:
            return False
    return True


def _uniqueness(conn, table, col) -> float:
    row = conn.execute(
        f"SELECT COUNT(DISTINCT {_q(col)}), COUNT({_q(col)}) FROM {_q(table)} WHERE {_q(col)} != ''"
    ).fetchone()
    distinct, total = row
    return (distinct / total) if total else 0.0


def _combined(cols: list[str]) -> str:
    """SQL expression concatenating several columns into one composite-key value."""
    return " || '\x1f' || ".join(_q(c) for c in cols)


def _composite_uniqueness(conn, table, cols: list[str]) -> float:
    """How unique the tuple of `cols` is in `table` (1.0 → a composite primary key,
    so joining on all of them is a 1:1 lookup with no fan-out)."""
    expr = _combined(cols)
    where = " AND ".join(f"{_q(c)} != ''" for c in cols)
    row = conn.execute(
        f"SELECT COUNT(DISTINCT {expr}), COUNT(*) FROM {_q(table)} WHERE {where}"
    ).fetchone()
    distinct, total = row
    return (distinct / total) if total else 0.0


def _composite_tuples(conn, table, cols: list[str], limit: int) -> set[tuple]:
    expr = ", ".join(_q(c) for c in cols)
    where = " AND ".join(f"{_q(c)} != ''" for c in cols)
    return {
        tuple(r) for r in conn.execute(
            f"SELECT DISTINCT {expr} FROM {_q(table)} WHERE {where} LIMIT {int(limit)}"
        ).fetchall()
    }


def _shared_key_columns(a: str, b: str, tables: dict[str, "TableInfo"]) -> list[tuple[str, str]]:
    """Key columns present in BOTH tables that refer to the same entity, matched by
    a non-empty shared stem (raceId~raceId, driverId~driverId). Bare `id` is
    excluded (empty stem) — it can't anchor a composite key by itself."""
    pairs: list[tuple[str, str]] = []
    for ca in tables[a].columns:
        if not _looks_like_fk(ca) or not _key_stem(ca):
            continue
        for cb in tables[b].columns:
            if _looks_like_fk(cb) and _key_stem(ca) == _key_stem(cb):
                pairs.append((ca, cb))
                break
    return pairs


def detect_joins(
    conn: sqlite3.Connection,
    tables: dict[str, TableInfo],
    sample: int = 500,
    min_overlap: float = 0.6,
    min_distinct: int = 2,
) -> list[JoinCandidate]:
    """Find likely `left.col → right.col` foreign keys via value overlap.
    Returns the best candidate per (left_table, right_table) pair, high-confidence
    first."""
    value_sets: dict[tuple[str, str], set[str]] = {}
    for t, info in tables.items():
        for c in info.columns:
            value_sets[(t, c)] = _distinct_values(conn, t, c, sample)

    # At most one join per *unordered* table pair — keep the best direction so we
    # don't emit both `a→b` and a spurious reverse `b→a` for the same two tables.
    best: dict[frozenset, JoinCandidate] = {}
    names = list(tables)
    for a in names:
        for b in names:
            if a == b:
                continue
            for ca in tables[a].columns:
                sa = value_sets[(a, ca)]
                if len(sa) < min_distinct:
                    continue
                for cb in tables[b].columns:
                    sb = value_sets[(b, cb)]
                    if not sb:
                        continue
                    overlap = len(sa & sb) / len(sa)
                    if overlap < min_overlap:
                        continue
                    uniq = _uniqueness(conn, b, cb)
                    if uniq < 0.9:        # right side should be roughly a key
                        continue
                    # Reject spurious overlaps between DIFFERENT entities. A valid
                    # join key is either key columns referring to the SAME entity
                    # (raceId~raceId, orders.user_id~users.id), or a shared
                    # NON-numeric dimension of the same name (country~country).
                    # `_keys_compatible` is applied even when the names are
                    # identical, because a bare `id` names no entity — `users.id`
                    # and `orders.id` are both `id` but must NOT join (that would
                    # beat the real `orders.user_id → users.id`). This also stops
                    # `statusId`~`raceId` and same-named MEASURES (points~points).
                    same_name = ca.lower() == cb.lower()
                    key_like = _looks_like_fk(ca) and _looks_like_fk(cb)
                    if key_like:
                        if not _keys_compatible(ca, cb, a, b):
                            continue
                    elif same_name and not _is_numeric_col(conn, b, cb):
                        pass                      # shared string dimension, e.g. country
                    else:
                        continue
                    name_bonus = 0.1 if same_name else 0.0
                    conf = min(1.0, overlap * 0.7 + uniq * 0.3 + name_bonus)
                    left_uniq = _uniqueness(conn, a, ca)
                    key = frozenset((a, b))
                    if key not in best or conf > best[key].confidence:
                        best[key] = JoinCandidate(a, ca, b, cb, round(overlap, 3),
                                                  round(uniq, 3), round(left_uniq, 3),
                                                  round(conf, 3))
    return sorted(best.values(), key=lambda c: c.confidence, reverse=True)


def detect_composite_joins(
    conn: sqlite3.Connection,
    tables: dict[str, TableInfo],
    sample: int = 3000,
    min_overlap: float = 0.6,
) -> list[JoinCandidate]:
    """Find COMPOSITE-key joins: two tables that share 2+ key columns whose
    combination is a unique key on at least one side. This connects fact ↔ detail
    tables (results ⋈ driver_standings on raceId+driverId) as a 1:1 lookup with no
    fan-out — something no single-column join can express."""
    out: list[JoinCandidate] = []
    names = list(tables)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pairs = _shared_key_columns(a, b, tables)
            if len(pairs) < 2:
                continue
            a_cols = [p[0] for p in pairs]
            b_cols = [p[1] for p in pairs]
            uniq_a = _composite_uniqueness(conn, a, a_cols)
            uniq_b = _composite_uniqueness(conn, b, b_cols)
            if max(uniq_a, uniq_b) < 0.9:
                continue          # neither side is a composite key → would fan out
            # Orient so the RIGHT (lookup) side is the unique one.
            if uniq_b >= uniq_a:
                lt, lc, rt, rc, ru, lu = a, a_cols, b, b_cols, uniq_b, uniq_a
            else:
                lt, lc, rt, rc, ru, lu = b, b_cols, a, a_cols, uniq_a, uniq_b
            left_tuples = _composite_tuples(conn, lt, lc, sample)
            right_tuples = _composite_tuples(conn, rt, rc, sample)
            if not left_tuples:
                continue
            overlap = len(left_tuples & right_tuples) / len(left_tuples)
            if overlap < min_overlap:
                continue
            conf = min(1.0, overlap * 0.6 + ru * 0.3 + 0.2)  # +structural bonus
            primary, *extra = list(zip(lc, rc))
            out.append(JoinCandidate(
                lt, primary[0], rt, primary[1], round(overlap, 3),
                round(ru, 3), round(lu, 3), round(conf, 3),
                extra_pairs=[tuple(e) for e in extra],
            ))
    return out


def detect_all_joins(
    conn: sqlite3.Connection,
    tables: dict[str, TableInfo],
) -> list[JoinCandidate]:
    """Single-column joins plus composite-key joins, best per table pair, ranked."""
    best: dict[frozenset, JoinCandidate] = {}
    for c in detect_joins(conn, tables) + detect_composite_joins(conn, tables):
        key = frozenset((c.left_table, c.right_table))
        # A composite join wins over a single-column one for the same pair (it's
        # the fan-out-free link); otherwise keep the higher confidence.
        cur = best.get(key)
        if (cur is None
                or (bool(c.extra_pairs) and not cur.extra_pairs)
                or (bool(c.extra_pairs) == bool(cur.extra_pairs) and c.confidence > cur.confidence)):
            best[key] = c
    return sorted(best.values(), key=lambda c: c.confidence, reverse=True)


# ── join plan + execution ────────────────────────────────────────────────────
class JoinStep(BaseModel):
    left_table: str
    left_col: str
    right_table: str
    right_col: str
    how: str = "left"   # "left" | "inner"
    # Extra (left_col, right_col) pairs for a composite join, ANDed with the
    # primary pair. Empty for a normal single-column join.
    extra_pairs: list[tuple[str, str]] = []

    @property
    def col_pairs(self) -> list[tuple[str, str]]:
        return [(self.left_col, self.right_col), *self.extra_pairs]


class JoinPlan(BaseModel):
    base_table: str
    steps: list[JoinStep] = []


class JoinError(ValueError):
    pass


def suggest_plan(
    tables: dict[str, TableInfo],
    candidates: list[JoinCandidate],
) -> tuple[JoinPlan, list[str]]:
    """Auto-build a plan that connects as many tables as possible into one wide
    table, so the combined dataset exposes every joinable column to the chart
    LLM. A maximum-confidence spanning tree (Prim's) rooted at the fact table.

    Returns (plan, unjoined) where `unjoined` are tables with no join path (they
    share no key with the rest, so their columns can't be included)."""
    if not tables:
        return JoinPlan(base_table=""), []

    # Base = the table that references the most others (the fact table), so LEFT
    # joins keep all its rows; tie-break by row count.
    out_degree: dict[str, int] = {}
    for c in candidates:
        out_degree[c.left_table] = out_degree.get(c.left_table, 0) + 1
    base = max(tables, key=lambda t: (out_degree.get(t, 0), tables[t].row_count))

    reachable = {base}
    steps: list[JoinStep] = []
    ranked = sorted(candidates, key=lambda c: c.confidence, reverse=True)
    changed = True
    while changed:
        changed = False
        for c in ranked:
            l_in, r_in = c.left_table in reachable, c.right_table in reachable
            if l_in == r_in:                     # both new or both known — skip
                continue
            # The table being brought in is the side NOT yet reachable. Only add
            # it when it attaches as a unique lookup (its own join key is ~unique),
            # otherwise it fans the fact table out into a many-to-many cartesian
            # (e.g. season standings keyed only on raceId) and corrupts every count.
            new_table = c.left_table if not l_in else c.right_table
            new_uniq = c.left_uniqueness if new_table == c.left_table else c.right_uniqueness
            if new_uniq < 0.9:
                continue
            steps.append(JoinStep(
                left_table=c.left_table, left_col=c.left_col,
                right_table=c.right_table, right_col=c.right_col, how="left",
                extra_pairs=[tuple(p) for p in c.extra_pairs],
            ))
            reachable.add(c.left_table)
            reachable.add(c.right_table)
            changed = True
            break

    unjoined = [t for t in tables if t not in reachable]
    return JoinPlan(base_table=base, steps=steps), unjoined


def _validate_plan(plan: JoinPlan, tables: dict[str, TableInfo]) -> None:
    def check(t, c):
        if t not in tables:
            raise JoinError(f"Unknown table '{t}'")
        if c not in tables[t].columns:
            raise JoinError(f"Unknown column '{c}' in table '{t}'")

    if plan.base_table not in tables:
        raise JoinError(f"Unknown base table '{plan.base_table}'")
    reachable = {plan.base_table}
    for s in plan.steps:
        for lc, rc in s.col_pairs:
            check(s.left_table, lc)
            check(s.right_table, rc)
        if s.how not in ("left", "inner"):
            raise JoinError(f"Invalid join type '{s.how}'")
        if s.left_table not in reachable and s.right_table not in reachable:
            raise JoinError(f"Join step is disconnected: {s.left_table}/{s.right_table}")
        reachable.add(s.left_table)
        reachable.add(s.right_table)


def execute_join(
    conn: sqlite3.Connection,
    plan: JoinPlan,
    tables: dict[str, TableInfo],
) -> tuple[list[str], list[dict]]:
    """Run the join and return (output_columns, rows). Colliding column names are
    disambiguated by prefixing the source table."""
    _validate_plan(plan, tables)

    # Each table joins exactly once. A step that would re-add an already-joined
    # table (a cyclic / redundant/false-positive join) is skipped so it can't
    # blow up into a cartesian product.
    joined = {plan.base_table}
    order = [plan.base_table]
    join_clauses: list[str] = []
    for s in plan.steps:
        if s.left_table in joined and s.right_table in joined:
            continue                                   # redundant / cyclic
        new = s.right_table if s.left_table in joined else s.left_table
        if new in joined:
            continue
        joined.add(new)
        order.append(new)
        jt = "INNER JOIN" if s.how == "inner" else "LEFT JOIN"
        on = " AND ".join(
            f"{_q(s.left_table)}.{_q(lc)} = {_q(s.right_table)}.{_q(rc)}"
            for lc, rc in s.col_pairs
        )
        join_clauses.append(f" {jt} {_q(new)} ON {on}")

    # unique output column names
    counts: dict[str, int] = {}
    for t in order:
        for c in tables[t].columns:
            counts[c] = counts.get(c, 0) + 1
    select_parts, out_cols = [], []
    for t in order:
        for c in tables[t].columns:
            out = c if counts[c] == 1 else f"{t}_{c}"
            select_parts.append(f"{_q(t)}.{_q(c)} AS {_q(out)}")
            out_cols.append(out)

    sql = f"SELECT {', '.join(select_parts)} FROM {_q(plan.base_table)}" + "".join(join_clauses)
    rows = [dict(zip(out_cols, r)) for r in conn.execute(sql).fetchall()]
    return out_cols, rows


def to_csv(columns: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
