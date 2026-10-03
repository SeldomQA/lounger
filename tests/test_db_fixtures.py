"""
Tests for the database fixture factories (``lounger.db_operation.fixtures``).

Regression context: ``create_mysql_fixture()`` resolved its default configuration
through ``ExtractVar().config``, which reads the ``global_test_config`` node —
while ``build_mysql_resource`` expects ``db_host`` / ``db_port`` / ``db_user`` /
``db_password`` / ``db_database``. A project following the documented top-level
layout therefore got ``None`` for every key and could not connect. The default is
now :func:`lounger.db_operation.fixtures._settings_source`, which accepts both
layouts.
"""
import pytest

from lounger.db_operation import fixtures
from lounger.settings import DictSettingsSource, settings


@pytest.fixture
def settings_values(monkeypatch):
    """
    Replace the settings sources with an in-memory mapping for one test.

    ``_settings_source`` reads ``lounger.settings`` at call time, so swapping the
    source list is enough to control what a project's config would contain.
    """
    source = DictSettingsSource({})
    monkeypatch.setattr(settings, "_sources", [source])
    return source.values


@pytest.fixture
def recorded_resource(monkeypatch):
    """Capture what the fixture factory passes to ``build_mysql_resource``."""
    captured = {}

    class FakeResource:
        def __enter__(self):
            return "db-handle"

        def __exit__(self, *exc):
            return False

    def fake_build(source, use_ssh_tunnel=None):
        captured["source"] = source
        captured["resolved"] = {
            key: (source(key) if callable(source) else source.get(key))
            for key in ("db_host", "db_port", "db_user", "db_password", "db_database")
        }
        return FakeResource()

    monkeypatch.setattr("lounger.db_operation.resource.build_mysql_resource", fake_build)
    return captured


def _consume(factory):
    """
    Drive a fixture factory's generator without pytest's fixture machinery.

    ``@pytest.fixture`` wraps the function, so the underlying generator is
    reached through ``__wrapped__``; this lets the tests assert exactly what the
    factory tells ``build_mysql_resource``.
    """
    return next(factory.__wrapped__())


# ── A1: the default configuration source ───────────────────────────────────

def test_settings_source_reads_top_level_db_keys(settings_values, recorded_resource):
    """The documented top-level layout must reach build_mysql_resource."""
    settings_values.update(
        {"db_host": "10.0.0.5", "db_port": 3307, "db_user": "root", "db_password": "p", "db_database": "guest3"}
    )

    factory = fixtures.create_mysql_fixture()
    assert _consume(factory) == "db-handle"

    assert recorded_resource["resolved"] == {
        "db_host": "10.0.0.5",
        "db_port": 3307,
        "db_user": "root",
        "db_password": "p",
        "db_database": "guest3",
    }


def test_settings_source_falls_back_to_the_global_test_config_node(settings_values, recorded_resource):
    """Credentials kept inside ``global_test_config`` keep working."""
    settings_values.update({"global_test_config": {"db_host": "node-host", "db_database": "node-db"}})

    _consume(fixtures.create_mysql_fixture())

    assert recorded_resource["resolved"]["db_host"] == "node-host"
    assert recorded_resource["resolved"]["db_database"] == "node-db"


def test_settings_source_prefers_top_level_over_node(settings_values, recorded_resource):
    settings_values.update(
        {"db_host": "top-level", "global_test_config": {"db_host": "from-node"}}
    )

    _consume(fixtures.create_mysql_fixture())

    assert recorded_resource["resolved"]["db_host"] == "top-level"


def test_explicit_config_source_still_wins(recorded_resource):
    factory = fixtures.create_mysql_fixture(config_source={"db_host": "explicit", "db_database": "d"})

    _consume(factory)

    assert recorded_resource["resolved"]["db_host"] == "explicit"


def test_explicit_kwargs_still_win_over_settings(settings_values, recorded_resource):
    settings_values.update({"db_host": "from-settings"})

    factory = fixtures.create_mysql_fixture(host="kwarg-host", user="u", database="d")
    _consume(factory)

    assert recorded_resource["resolved"]["db_host"] == "kwarg-host"


def test_settings_source_is_a_plain_callable(settings_values):
    """``build_mysql_resource`` calls the source with a key."""
    settings_values.update({"db_host": "1.2.3.4"})

    assert fixtures._settings_source("db_host") == "1.2.3.4"
    assert fixtures._settings_source("missing_key") is None


# ── unchanged contracts of the other factories ─────────────────────────────

def test_sqlite_fixture_yields_and_closes(monkeypatch):
    closed = []

    class FakeSQLite:
        def __init__(self, db_path, **kwargs):
            self.db_path = db_path

        def close(self):
            closed.append(self.db_path)

    monkeypatch.setattr("lounger.db_operation.sqlite_db.SQLiteDB", FakeSQLite)

    factory = fixtures.create_sqlite_fixture(db_path=":memory:")
    handle = _consume(factory)

    assert isinstance(handle, FakeSQLite)
    assert closed == [":memory:"]
