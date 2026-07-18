import pytest

from pipeline.multi_csv import (
    load_tables, detect_joins, detect_composite_joins, detect_all_joins,
    execute_join, suggest_plan, to_csv,
    JoinPlan, JoinStep, JoinError,
)

CUSTOMERS = "id,name,country\n1,Alice,US\n2,Bob,UK\n3,Carol,US\n"
ORDERS = "order_id,customer_id,amount\n101,1,50\n102,1,30\n103,2,80\n104,3,20\n"
PRODUCTS = "product_id,label,price\np1,Widget,9.99\np2,Gadget,19.99\n"


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return (name, str(p))


@pytest.fixture
def db(tmp_path):
    files = [
        _write(tmp_path, "customers.csv", CUSTOMERS),
        _write(tmp_path, "orders.csv", ORDERS),
    ]
    return load_tables(files)


class TestLoad:
    def test_tables_and_columns(self, db):
        _, tables = db
        assert set(tables) == {"customers", "orders"}
        assert tables["customers"].columns == ["id", "name", "country"]
        assert tables["orders"].row_count == 4

    def test_table_name_sanitized_and_unique(self, tmp_path):
        files = [
            _write(tmp_path, "Sales 2024.csv", "a,b\n1,2\n"),
            _write(tmp_path, "Sales-2024.csv", "a,b\n3,4\n"),
        ]
        _, tables = load_tables(files)
        names = sorted(tables)
        assert names[0] == "sales_2024" and names[1] == "sales_2024_2"


class TestDetect:
    def test_finds_foreign_key(self, db):
        conn, tables = db
        cands = detect_joins(conn, tables)
        # orders.customer_id → customers.id
        top = next(c for c in cands if c.left_table == "orders" and c.right_table == "customers")
        assert top.left_col == "customer_id" and top.right_col == "id"
        assert top.overlap == 1.0 and top.right_uniqueness == 1.0

    def test_one_candidate_per_table_pair(self, db):
        conn, tables = db
        cands = detect_joins(conn, tables)
        pairs = [frozenset((c.left_table, c.right_table)) for c in cands]
        assert len(pairs) == len(set(pairs))  # no duplicate/reverse pair

    def test_rejects_measure_overlapping_a_key(self, tmp_path):
        # `number` (a measure) overlaps `standing_id` values but isn't a key name
        conn, tables = load_tables([
            _write(tmp_path, "results.csv", "result_id,number,driver_id\nr1,1,d1\nr2,2,d2\nr3,3,d1\n"),
            _write(tmp_path, "standings.csv", "standing_id,points\n1,25\n2,18\n3,10\n"),
        ])
        cands = detect_joins(conn, tables)
        # no candidate should join `number` → `standing_id`
        assert all(not (c.left_col == "number" or c.right_col == "number") for c in cands)

    def test_id_named_fk_still_detected(self, tmp_path):
        conn, tables = load_tables([
            _write(tmp_path, "orders.csv", "order_id,customer_id\no1,c1\no2,c2\n"),
            _write(tmp_path, "customers.csv", "id,name\nc1,Alice\nc2,Bob\n"),
        ])
        cands = detect_joins(conn, tables)
        assert any(c.left_col == "customer_id" and c.right_col == "id" for c in cands)

    def test_no_spurious_join_on_measures(self, tmp_path):
        # amount values don't overlap another table's key → no join
        conn, tables = load_tables([
            _write(tmp_path, "a.csv", "k,amount\nx,10\ny,20\n"),
            _write(tmp_path, "b.csv", "k,total\np,999\nq,888\n"),
        ])
        cands = detect_joins(conn, tables)
        assert all(not (c.left_col == "amount" or c.right_col == "amount") for c in cands)

    def test_rejects_different_entity_keys_that_overlap(self, tmp_path):
        # statusId and raceId are both key-named small ints that overlap by value,
        # but refer to different entities → must NOT be joined together.
        conn, tables = load_tables([
            _write(tmp_path, "status.csv", "statusId,label\n1,Finished\n2,Accident\n3,Engine\n"),
            _write(tmp_path, "races.csv", "raceId,year\n1,2016\n2,2016\n3,2016\n"),
        ])
        cands = detect_joins(conn, tables)
        assert all(not {c.left_col, c.right_col} == {"statusId", "raceId"} for c in cands)

    def test_rejects_same_named_measure_join(self, tmp_path):
        # two 'points' columns share a name and overlap by value, but points is a
        # numeric measure, not a key → must not create a join.
        conn, tables = load_tables([
            _write(tmp_path, "results.csv", "resultId,points\n1,10\n2,25\n3,18\n"),
            _write(tmp_path, "standings.csv", "standingId,points\n1,10\n2,25\n3,18\n"),
        ])
        cands = detect_joins(conn, tables)
        assert all(not (c.left_col == "points" and c.right_col == "points") for c in cands)

    def test_two_id_pks_do_not_join_directly(self, tmp_path):
        # users.id (user PK) and orders.id (order PK) are both bare `id` and their
        # integers overlap, but a bare `id` names no entity — they must NOT join.
        # The real link is orders.user_id -> users.id, which must win instead.
        conn, tables = load_tables([
            _write(tmp_path, "users.csv", "id,name\n1,Alice\n2,Bob\n3,Carol\n"),
            _write(tmp_path, "orders.csv", "id,user_id,amount\n1,1,50\n2,1,30\n3,2,80\n"),
        ])
        cands = detect_joins(conn, tables)
        assert all(not (c.left_col == "id" and c.right_col == "id") for c in cands)
        assert any(c.left_col == "user_id" and c.right_col == "id" for c in cands)

    def test_allows_same_named_string_dimension(self, tmp_path):
        # a shared NON-numeric dimension (country) is a legitimate join key
        conn, tables = load_tables([
            _write(tmp_path, "sales.csv", "id,country\n1,US\n2,UK\n"),
            _write(tmp_path, "info.csv", "country,gdp\nUS,21\nUK,3\n"),
        ])
        cands = detect_joins(conn, tables)
        assert any(c.left_col == "country" and c.right_col == "country" for c in cands)

    def test_fk_referencing_tail_of_large_dimension(self, tmp_path):
        # Regression: a FK that references only the TAIL of a dimension table larger
        # than the sample cap (sprint_results.raceId → the most recent races) must
        # still be detected. Two independently-capped samples would never intersect
        # (races' sample is raceId 1..cap, the FK points at raceId cap+..) → overlap 0.
        races = "raceId,year\n" + "".join(f"{i},{1950 + i // 20}\n" for i in range(1, 1126))
        sprint = "raceId,driverId\n" + "".join(
            f"{rid},{d}\n" for rid in range(1050, 1110) for d in range(1, 7)
        )
        conn, tables = load_tables([
            _write(tmp_path, "sprint_results.csv", sprint),
            _write(tmp_path, "races.csv", races),
        ])
        cands = detect_joins(conn, tables, sample=500)
        top = next(c for c in cands
                   if c.left_table == "sprint_results" and c.right_table == "races")
        assert top.left_col == "raceId" and top.right_col == "raceId"
        assert top.overlap == 1.0
        # and it plans + joins without fan-out (all 360 sprint rows preserved)
        plan, unjoined = suggest_plan(tables, cands)
        assert unjoined == []
        _, rows = execute_join(conn, plan, tables)
        assert len(rows) == 360


class TestSuggestPlan:
    def test_connects_all_tables(self, tmp_path):
        # results (fact) references races and drivers → one wide table
        conn, tables = load_tables([
            _write(tmp_path, "results.csv", "result_id,race_id,driver_id,points\nr1,ra1,d1,25\nr2,ra1,d2,18\nr3,ra2,d1,10\n"),
            _write(tmp_path, "races.csv", "race_id,circuit\nra1,Monza\nra2,Spa\n"),
            _write(tmp_path, "drivers.csv", "driver_id,driver_name\nd1,Alice\nd2,Bob\n"),
        ])
        cands = detect_joins(conn, tables)
        plan, unjoined = suggest_plan(tables, cands)
        assert plan.base_table == "results"
        assert unjoined == []
        # the joined table has every column from all three tables
        cols, rows = execute_join(conn, plan, tables)
        for c in ["result_id", "points", "circuit", "driver_name"]:
            assert c in cols
        assert len(rows) == 3  # fact rows preserved (left joins)
        by = {r["result_id"]: r for r in rows}
        assert by["r1"]["circuit"] == "Monza" and by["r1"]["driver_name"] == "Alice"

    def test_reports_unjoinable_table(self, tmp_path):
        conn, tables = load_tables([
            _write(tmp_path, "a.csv", "id,x\n1,10\n2,20\n"),
            _write(tmp_path, "b.csv", "a_id,y\n1,foo\n2,bar\n"),
            _write(tmp_path, "lonely.csv", "z,w\nqq,100\nrr,200\n"),   # shares no key
        ])
        cands = detect_joins(conn, tables)
        _, unjoined = suggest_plan(tables, cands)
        assert unjoined == ["lonely"]

    def test_skips_fanout_table_to_preserve_fact_grain(self, tmp_path):
        # standings has MANY rows per raceId — joining it on raceId alone would
        # fan the 3 fact rows into a cartesian. It must be left unjoined instead.
        conn, tables = load_tables([
            _write(tmp_path, "results.csv",
                   "resultId,raceId,driverId\nr1,ra1,d1\nr2,ra1,d2\nr3,ra2,d1\n"),
            _write(tmp_path, "races.csv", "raceId,year\nra1,2016\nra2,2016\n"),
            _write(tmp_path, "drivers.csv", "driverId,surname\nd1,Alice\nd2,Bob\n"),
            _write(tmp_path, "standings.csv",
                   "standingId,raceId,points\ns1,ra1,10\ns2,ra1,8\ns3,ra2,25\n"),
        ])
        cands = detect_joins(conn, tables)
        plan, unjoined = suggest_plan(tables, cands)
        assert "standings" in unjoined
        _, rows = execute_join(conn, plan, tables)
        assert len(rows) == 3  # fact grain preserved, no fan-out blow-up


class TestExecute:
    def test_left_join_flattens(self, db):
        conn, tables = db
        plan = JoinPlan(base_table="orders", steps=[
            JoinStep(left_table="orders", left_col="customer_id",
                     right_table="customers", right_col="id"),
        ])
        cols, rows = execute_join(conn, plan, tables)
        assert cols == ["order_id", "customer_id", "amount", "id", "name", "country"]
        assert len(rows) == 4
        by_order = {r["order_id"]: r for r in rows}
        assert by_order["101"]["name"] == "Alice" and by_order["101"]["country"] == "US"
        assert by_order["103"]["name"] == "Bob"

    def test_colliding_columns_get_prefixed(self, tmp_path):
        conn, tables = load_tables([
            _write(tmp_path, "orders.csv", "id,name,cust\n1,OrderA,c1\n"),
            _write(tmp_path, "customers.csv", "id,name\nc1,Alice\n"),
        ])
        plan = JoinPlan(base_table="orders", steps=[
            JoinStep(left_table="orders", left_col="cust",
                     right_table="customers", right_col="id"),
        ])
        cols, rows = execute_join(conn, plan, tables)
        # both tables have id + name → prefixed
        assert "orders_id" in cols and "customers_id" in cols
        assert "orders_name" in cols and "customers_name" in cols
        assert rows[0]["orders_name"] == "OrderA" and rows[0]["customers_name"] == "Alice"

    def test_validation_rejects_unknown(self, db):
        conn, tables = db
        with pytest.raises(JoinError):
            execute_join(conn, JoinPlan(base_table="nope"), tables)
        with pytest.raises(JoinError):
            execute_join(conn, JoinPlan(base_table="orders", steps=[
                JoinStep(left_table="orders", left_col="ghost",
                         right_table="customers", right_col="id"),
            ]), tables)

    def test_redundant_cyclic_step_is_skipped(self, db):
        # a second step that re-joins the base table must not explode the result
        conn, tables = db
        plan = JoinPlan(base_table="orders", steps=[
            JoinStep(left_table="orders", left_col="customer_id", right_table="customers", right_col="id"),
            JoinStep(left_table="customers", left_col="id", right_table="orders", right_col="customer_id"),
        ])
        _, rows = execute_join(conn, plan, tables)
        assert len(rows) == 4  # not a cartesian blow-up

    def test_steps_are_order_independent(self, tmp_path):
        # Regression: a plan whose steps are both anchored on a NON-base table, listed
        # so the step touching the base comes last, must still validate + execute — the
        # graph (races—sprint_results—status) is connected regardless of step order.
        conn, tables = load_tables([
            _write(tmp_path, "races.csv", "raceId,year\nra1,2021\nra2,2021\n"),
            _write(tmp_path, "status.csv", "statusId,label\n1,Finished\n2,Retired\n"),
            _write(tmp_path, "sprint_results.csv",
                   "raceId,driverId,statusId\nra1,d1,1\nra1,d2,2\nra2,d1,1\n"),
        ])
        # base is races; the step reaching races is listed SECOND (was "disconnected")
        plan = JoinPlan(base_table="races", steps=[
            JoinStep(left_table="sprint_results", left_col="statusId",
                     right_table="status", right_col="statusId"),
            JoinStep(left_table="sprint_results", left_col="raceId",
                     right_table="races", right_col="raceId"),
        ])
        cols, rows = execute_join(conn, plan, tables)  # must not raise "disconnected"
        assert "label" in cols and "year" in cols
        assert len(rows) == 3  # every sprint row, with its race + status attached

    def test_to_csv_roundtrips(self, db):
        conn, tables = db
        plan = JoinPlan(base_table="orders", steps=[
            JoinStep(left_table="orders", left_col="customer_id",
                     right_table="customers", right_col="id"),
        ])
        cols, rows = execute_join(conn, plan, tables)
        text = to_csv(cols, rows)
        assert text.splitlines()[0] == "order_id,customer_id,amount,id,name,country"
        assert "Alice" in text

    def test_composite_step_ands_all_pairs(self, tmp_path):
        # a composite join on (raceId, driverId) must match 1:1, not fan out
        conn, tables = load_tables([
            _write(tmp_path, "results.csv",
                   "resultId,raceId,driverId,points\n1,r1,d1,25\n2,r1,d2,18\n3,r2,d1,10\n"),
            _write(tmp_path, "standings.csv",
                   "standingId,raceId,driverId,wins\ns1,r1,d1,1\ns2,r1,d2,0\ns3,r2,d1,2\n"),
        ])
        plan = JoinPlan(base_table="results", steps=[
            JoinStep(left_table="results", left_col="raceId",
                     right_table="standings", right_col="raceId",
                     extra_pairs=[("driverId", "driverId")]),
        ])
        cols, rows = execute_join(conn, plan, tables)
        assert len(rows) == 3          # no fan-out
        assert "wins" in cols
        by = {r["resultId"]: r for r in rows}
        assert by["1"]["wins"] == "1" and by["3"]["wins"] == "2"


class TestComposite:
    def _f1_tables(self, tmp_path):
        return load_tables([
            _write(tmp_path, "results.csv",
                   "resultId,raceId,driverId,constructorId\n1,r1,d1,c1\n2,r1,d2,c1\n3,r2,d1,c2\n"),
            _write(tmp_path, "races.csv", "raceId,year\nr1,2016\nr2,2016\n"),
            _write(tmp_path, "drivers.csv", "driverId,surname\nd1,Alice\nd2,Bob\n"),
            _write(tmp_path, "constructors.csv", "constructorId,name\nc1,Merc\nc2,Ferrari\n"),
            # detail table keyed on (raceId, driverId) — fan-out on either alone
            _write(tmp_path, "driver_standings.csv",
                   "driverStandingsId,raceId,driverId,wins\nds1,r1,d1,1\nds2,r1,d2,0\nds3,r2,d1,2\n"),
        ])

    def test_detects_composite_key(self, tmp_path):
        conn, tables = self._f1_tables(tmp_path)
        comps = detect_composite_joins(conn, tables)
        # results ⋈ driver_standings on raceId + driverId
        c = next(c for c in comps
                 if {c.left_table, c.right_table} == {"results", "driver_standings"})
        pairs = set(c.all_pairs)
        assert pairs == {("raceId", "raceId"), ("driverId", "driverId")}

    def test_detect_all_includes_standings_and_no_fanout(self, tmp_path):
        conn, tables = self._f1_tables(tmp_path)
        cands = detect_all_joins(conn, tables)
        plan, unjoined = suggest_plan(tables, cands)
        assert unjoined == []                       # driver_standings now joins in
        cols, rows = execute_join(conn, plan, tables)
        assert len(rows) == 3                        # fact grain preserved
        assert "wins" in cols and "surname" in cols and "year" in cols
        by = {r["resultId"]: r for r in rows}
        assert by["1"]["surname"] == "Alice" and by["1"]["wins"] == "1"
        assert by["3"]["wins"] == "2"

    def test_no_composite_when_only_one_shared_key(self, tmp_path):
        # orders/customers share just one key → not a composite
        conn, tables = load_tables([
            _write(tmp_path, "orders.csv", "order_id,customer_id\no1,c1\no2,c2\n"),
            _write(tmp_path, "customers.csv", "customer_id,name\nc1,Al\nc2,Bo\n"),
        ])
        assert detect_composite_joins(conn, tables) == []
