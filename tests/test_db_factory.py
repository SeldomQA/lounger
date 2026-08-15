"""
Tests for DatabaseFactory and the database fixture factories.
"""
import sys

from lounger.db_operation.factory import DatabaseFactory
from lounger.db_operation.fixtures import (
    create_mssql_fixture,
    create_mysql_fixture,
    create_postgres_fixture,
    create_sqlite_fixture,
)
from lounger.db_operation.resource import MySQLConnectionConfig, SSHTunnelConfig


class FakeDB:
    """Records constructor kwargs and mimics close()."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False

    def close(self):
        self.closed = True


class FakeResource:
    """Stand-in for MySQLResource: records config and returns a FakeDB."""

    def __init__(self):
        self.connection = None
        self.tunnel = None
        self.calls = []

    def connect(self):
        self.calls.append((self.connection, self.tunnel))
        return FakeDB(connection=self.connection, tunnel=self.tunnel)


# ── DatabaseFactory ─────────────────────────────────────────────────────────

def test_database_factory_mysql_with_tunnel(monkeypatch):
    resource = FakeResource()

    def fake_factory(connection, tunnel):
        resource.connection = connection
        resource.tunnel = tunnel
        return resource

    monkeypatch.setattr("lounger.db_operation.factory.MySQLResource", fake_factory)

    connection = MySQLConnectionConfig(
        host="db.example.com", port=3306, user="u", password="p", database="d"
    )
    tunnel = SSHTunnelConfig(
        ssh_host="jump.example.com", ssh_port=22, ssh_user="tester",
        remote_host="mysql.internal", remote_port=3306,
    )

    db = DatabaseFactory.mysql(connection=connection, tunnel=tunnel)

    assert resource.calls == [(connection, tunnel)]
    assert db.kwargs["connection"] is connection
    assert db.kwargs["tunnel"] is tunnel


def test_database_factory_mysql_without_tunnel(monkeypatch):
    resource = FakeResource()

    def fake_factory(connection, tunnel):
        resource.connection = connection
        resource.tunnel = tunnel
        return resource

    monkeypatch.setattr("lounger.db_operation.factory.MySQLResource", fake_factory)

    connection = MySQLConnectionConfig(
        host="h", port=3306, user="u", password="p", database="d"
    )
    DatabaseFactory.mysql(connection=connection)

    assert resource.calls == [(connection, None)]


def test_database_factory_postgres(monkeypatch):
    monkeypatch.setattr("lounger.db_operation.postgres_db.PostgresDB", FakeDB)

    db = DatabaseFactory.postgres(host="h", port=5432, database="d", user="u", password="p")

    assert db.kwargs == {"host": "h", "port": 5432, "database": "d", "user": "u", "password": "p"}


def test_database_factory_mssql(monkeypatch):
    monkeypatch.setattr("lounger.db_operation.mssql_db.MSSQLDB", FakeDB)

    db = DatabaseFactory.mssql(server="s", user="u", password="p", database="d")

    assert db.kwargs == {
        "server": "s", "user": "u", "password": "p", "database": "d", "charset": "utf8mb4",
    }


def test_db_driver_modules_importable_without_drivers():
    """Importing the db modules must NOT pull in pymssql / psycopg2 / pymongo."""
    before = set(sys.modules)
    import lounger.db_operation.mongo_db  # noqa: F401
    import lounger.db_operation.mssql_db  # noqa: F401
    import lounger.db_operation.postgres_db  # noqa: F401
    imported = set(sys.modules) - before
    assert "pymssql" not in imported
    assert "psycopg2" not in imported
    assert "pymongo" not in imported


# ── fixture factories ───────────────────────────────────────────────────────

def _run_fixture(fixture):
    """Drive a pytest-9-wrapped fixture function and return (db, generator).

    pytest 9 wraps fixture functions in FixtureFunctionDefinition; the
    original generator function is available via ``._fixture_function``.
    """
    gen = fixture._fixture_function()
    return next(gen), gen


def test_create_mysql_fixture_yields_and_closes(monkeypatch):
    class FakeResourceCtx:
        def __init__(self):
            self.entered = False
            self.exited = False

        def __enter__(self):
            self.entered = True
            return FakeDB(db="mysql")

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.exited = True
            return False

    resource = FakeResourceCtx()
    monkeypatch.setattr(
        "lounger.db_operation.resource.build_mysql_resource",
        lambda source: resource,
    )

    fixture = create_mysql_fixture(config_source=lambda key: "value")
    db, gen = _run_fixture(fixture)

    assert resource.entered
    assert db.kwargs == {"db": "mysql"}

    gen.close()
    assert resource.exited


def test_create_mysql_fixture_default_config_source(monkeypatch):
    """Without config_source, the fixture resolves settings via ExtractVar().config."""
    captured = {}

    class FakeResourceCtx:
        def __enter__(self):
            return FakeDB()

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    def fake_build(source):
        captured["source"] = source
        return FakeResourceCtx()

    monkeypatch.setattr("lounger.db_operation.resource.build_mysql_resource", fake_build)

    fixture = create_mysql_fixture()
    _, gen = _run_fixture(fixture)
    gen.close()

    assert callable(captured["source"])


def test_create_mysql_fixture_with_explicit_kwargs(monkeypatch):
    """Explicit connection kwargs are mapped to the resource source keys."""
    captured = {}

    class FakeResourceCtx:
        def __enter__(self):
            return FakeDB()

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    def fake_build(source):
        captured["source"] = source
        return FakeResourceCtx()

    monkeypatch.setattr("lounger.db_operation.resource.build_mysql_resource", fake_build)

    fixture = create_mysql_fixture(
        host="localhost", port=3306, user="root",
        password="198876", database="guest3",
    )
    _, gen = _run_fixture(fixture)
    gen.close()

    assert captured["source"]["db_host"] == "localhost"
    assert captured["source"]["db_port"] == 3306
    assert captured["source"]["db_user"] == "root"
    assert captured["source"]["db_password"] == "198876"
    assert captured["source"]["db_database"] == "guest3"


def test_create_mysql_fixture_kwargs_with_ssh_tunnel(monkeypatch):
    """Providing ssh_host + remote_db_host enables the SSH tunnel config."""
    captured = {}

    class FakeResourceCtx:
        def __enter__(self):
            return FakeDB()

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    def fake_build(source):
        captured["source"] = source
        return FakeResourceCtx()

    monkeypatch.setattr("lounger.db_operation.resource.build_mysql_resource", fake_build)

    fixture = create_mysql_fixture(
        host="127.0.0.1", user="u", password="p", database="d",
        ssh_host="jump.example.com", ssh_port=22, ssh_user="tester",
        remote_db_host="mysql.internal", remote_db_port=3306,
    )
    _, gen = _run_fixture(fixture)
    gen.close()

    assert captured["source"]["ssh_host"] == "jump.example.com"
    assert captured["source"]["remote_db_host"] == "mysql.internal"


def test_create_mysql_fixture_config_source_wins_over_kwargs(monkeypatch):
    captured = []

    class FakeResourceCtx:
        def __enter__(self):
            return FakeDB()

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    def fake_build(source):
        captured.append(source)
        return FakeResourceCtx()

    monkeypatch.setattr("lounger.db_operation.resource.build_mysql_resource", fake_build)

    fixture = create_mysql_fixture(config_source={"db_host": "from_source"}, host="from_kwargs")
    _, gen = _run_fixture(fixture)
    gen.close()

    assert captured == [{"db_host": "from_source"}]


def test_create_postgres_fixture_yields_and_closes(monkeypatch):
    monkeypatch.setattr(
        "lounger.db_operation.factory.DatabaseFactory.postgres",
        staticmethod(lambda **kwargs: FakeDB(**kwargs)),
    )

    fixture = create_postgres_fixture(host="h", port=5432, database="d", user="u", password="p")
    db, gen = _run_fixture(fixture)

    assert db.kwargs == {"host": "h", "port": 5432, "database": "d", "user": "u", "password": "p"}
    assert not db.closed

    gen.close()
    assert db.closed


def test_create_mssql_fixture_yields_and_closes(monkeypatch):
    monkeypatch.setattr(
        "lounger.db_operation.factory.DatabaseFactory.mssql",
        staticmethod(lambda **kwargs: FakeDB(**kwargs)),
    )

    fixture = create_mssql_fixture(server="s", user="u", password="p", database="d")
    db, gen = _run_fixture(fixture)

    assert db.kwargs["server"] == "s"
    assert not db.closed

    gen.close()
    assert db.closed


def test_db_classes_support_context_manager():
    """All DB wrappers inherit context-manager support from SQLBase."""
    from lounger.db_operation import MySQLDB, SQLiteDB
    from lounger.db_operation.mssql_db import MSSQLDB
    from lounger.db_operation.postgres_db import PostgresDB

    for cls in (MySQLDB, SQLiteDB, MSSQLDB, PostgresDB):
        assert hasattr(cls, "__enter__"), cls.__name__
        assert hasattr(cls, "__exit__"), cls.__name__


def test_sqlbase_context_manager_closes_on_exit():
    """`with db as conn:` returns the connection and closes it on exit."""
    from lounger.db_operation.base_db import SQLBase

    class FakeConn(SQLBase):
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    with FakeConn() as conn:
        assert isinstance(conn, FakeConn)
        assert not conn.closed

    assert conn.closed


def test_sqlbase_context_manager_closes_on_error():
    """The connection is closed even when the body raises."""
    from lounger.db_operation.base_db import SQLBase

    class FakeConn(SQLBase):
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    conn = FakeConn()
    try:
        with conn:
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert conn.closed


def test_create_sqlite_fixture_yields_and_closes(monkeypatch):
    monkeypatch.setattr("lounger.db_operation.sqlite_db.SQLiteDB", FakeDB)

    fixture = create_sqlite_fixture(db_path=":memory:")
    db, gen = _run_fixture(fixture)

    assert db.kwargs == {"db_path": ":memory:"}
    assert not db.closed

    gen.close()
    assert db.closed
