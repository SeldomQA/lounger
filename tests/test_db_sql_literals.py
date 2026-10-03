"""
Tests for SQL value rendering (``lounger.db_operation.base_db.SQLBase``).

Regression context: values were interpolated into the statement verbatim
(``f"{key}='{value}'"``), so a value containing a quote produced a syntax error
and any value could change the meaning of the statement. ``insert_data`` also
rewrote the *caller's* dict in place while quoting, so reusing one dict produced
doubled quotes.
"""
import pytest

from lounger.db_operation.base_db import SQLBase
from lounger.db_operation.sqlite_db import SQLiteDB


# ── value literals ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "null"),
        (1, "1"),
        (0, "0"),
        (-7, "-7"),
        (1.5, "1.5"),
        (True, "true"),
        (False, "false"),
        ("plain", "'plain'"),
        ("", "''"),
    ],
)
def test_value_literal_scalar_rendering(value, expected):
    assert SQLBase.value_literal(value) == expected


def test_value_literal_escapes_embedded_quotes():
    """The classic failure: a name with an apostrophe used to break the SQL."""
    assert SQLBase.value_literal("O'Brien") == "'O''Brien'"
    assert SQLBase.value_literal("a'b'c") == "'a''b''c'"


def test_value_literal_neutralizes_quote_injection():
    payload = "x' OR '1'='1"
    rendered = SQLBase.value_literal(payload)

    assert rendered == "'x'' OR ''1''=''1'"
    # every embedded quote is doubled, so the payload stays inside the literal
    inner = rendered[1:-1]
    assert inner.replace("''", "") == payload.replace("'", "")
    assert inner.count("'") == payload.count("'") * 2


def test_value_literal_keeps_non_ascii_and_specials():
    assert SQLBase.value_literal("张三") == "'张三'"
    assert SQLBase.value_literal("a%b_c") == "'a%b_c'"


# ── SET / WHERE clauses ────────────────────────────────────────────────────

def test_dict_to_str_renders_set_clause():
    assert SQLBase.dict_to_str({"name": "O'Brien", "age": 3, "note": None}) == (
        "name='O''Brien',age=3,note=null"
    )


def test_dict_to_str_and_renders_where_clause():
    assert SQLBase.dict_to_str_and({"id": 1, "name": "a'b"}) == "id=1 and name='a''b'"


def test_insert_clause_renders_columns_and_values():
    assert SQLBase.insert_clause({"a": 1, "b": "x'y", "c": None}) == ("a,b,c", "1,'x''y',null")


def test_insert_clause_does_not_modify_the_input():
    data = {"name": "O'Brien", "age": 3}
    snapshot = dict(data)

    SQLBase.insert_clause(data)
    SQLBase.insert_clause(data)

    assert data == snapshot, "insert_clause mutated the caller's dict"


def test_insert_clause_rejects_empty_data():
    with pytest.raises(ValueError, match="at least one column"):
        SQLBase.insert_clause({})


# ── end to end against SQLite (no external database required) ──────────────

@pytest.fixture
def sqlite_db():
    db = SQLiteDB(":memory:")
    db.execute_sql("create table person (id integer primary key, name text, age integer, note text)")
    try:
        yield db
    finally:
        db.close()


def test_sqlite_insert_and_select_with_quoted_values(sqlite_db):
    """A value containing an apostrophe must round-trip unchanged."""
    row = {"id": 1, "name": "O'Brien", "age": 30, "note": None}

    sqlite_db.insert_data("person", row)

    assert sqlite_db.query_one("select name from person where id=1") == ("O'Brien",)
    assert sqlite_db.select_data("person", {"name": "O'Brien"}, one=True)[1] == "O'Brien"


def test_sqlite_insert_does_not_corrupt_a_reused_dict(sqlite_db):
    """The same dict reused across inserts must not accumulate quotes."""
    row = {"id": 2, "name": "plain", "age": 1, "note": "x"}
    snapshot = dict(row)

    sqlite_db.insert_data("person", row)
    row["id"] = 6
    sqlite_db.insert_data("person", row)

    assert row == {**snapshot, "id": 6}, "insert_data rewrote the caller's dict"
    assert sqlite_db.query_sql("select id, name from person order by id") == [(2, "plain"), (6, "plain")]


def test_sqlite_update_and_delete_use_escaped_literals(sqlite_db):
    sqlite_db.insert_data("person", {"id": 3, "name": "before", "age": 1, "note": None})

    sqlite_db.update_data("person", {"name": "O'Hara"}, {"id": 3})

    assert sqlite_db.query_one("select name from person where id=3") == ("O'Hara",)
    sqlite_db.delete_data("person", {"name": "O'Hara"})
    assert sqlite_db.query_one("select count(*) from person") == (0,)


def test_sqlite_injection_payload_stays_data(sqlite_db):
    """A classic payload must be stored as text, not executed as SQL."""
    sqlite_db.insert_data("person", {"id": 4, "name": "x' OR '1'='1", "age": 1, "note": None})
    sqlite_db.insert_data("person", {"id": 5, "name": "keep", "age": 2, "note": None})

    rows = sqlite_db.query_sql("select id from person order by id")

    assert rows == [(4,), (5,)]
    assert sqlite_db.query_one("select count(*) from person") == (2,)
