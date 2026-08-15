"""
Standard pytest fixtures for database connections.

Usage in a project's ``conftest.py``::

    from lounger.utils.variables import ExtractVar
    from lounger.db_operation.fixtures import create_mysql_fixture

    mysql_db = create_mysql_fixture(config_source=ExtractVar().config)
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest


def _build_mysql_resource_from_kwargs(kwargs: dict) -> Any:
    """
    Build a MySQLResource from explicit fixture kwargs.

    The kwargs are mapped to the ``build_mysql_resource`` source keys. An SSH
    tunnel is enabled automatically when ``ssh_host`` + ``remote_db_host`` are
    provided.

    :param kwargs: connection kwargs (``host`` / ``port`` / ``user`` /
        ``password`` / ``database`` / ``charset``, plus optional SSH tunnel
        keys ``ssh_host`` / ``ssh_port`` / ``ssh_user`` / ``remote_db_host`` /
        ``remote_db_port`` / ``ssh_private_key`` / ``ssh_password`` /
        ``local_db_port``).
    :return: A :class:`lounger.db_operation.resource.MySQLResource`.
    """
    from lounger.db_operation.resource import build_mysql_resource

    source = {
        "db_host": kwargs.get("host", "127.0.0.1"),
        "db_port": kwargs.get("port", 3306),
        "db_user": kwargs.get("user"),
        "db_password": kwargs.get("password"),
        "db_database": kwargs.get("database"),
        "db_charset": kwargs.get("charset", "utf8mb4"),
        "ssh_host": kwargs.get("ssh_host"),
        "ssh_port": kwargs.get("ssh_port"),
        "ssh_user": kwargs.get("ssh_user"),
        "remote_db_host": kwargs.get("remote_db_host"),
        "remote_db_port": kwargs.get("remote_db_port"),
        "ssh_private_key": kwargs.get("ssh_private_key"),
        "ssh_password": kwargs.get("ssh_password"),
        "local_db_port": kwargs.get("local_db_port"),
    }
    return build_mysql_resource(source)


def create_mysql_fixture(
    scope: str = "session",
    config_source: Callable[[str], Any] | None = None,
    **connection_kwargs,
):
    """
    Create a pytest fixture that provides a managed MySQL connection.

    The connection (and an optional SSH tunnel) is built and torn down through
    :class:`lounger.db_operation.resource.MySQLResource`, so no manual
    connect/close/tunnel code is needed in the business project.

    Configuration — pick one, in this priority order:

    1. ``config_source``: a callable ``(key) -> value`` or a mapping with the
       ``build_mysql_resource`` keys (``db_host`` / ``db_port`` / ``db_user`` /
       ``db_password`` / ``db_database``, plus optional SSH tunnel keys);
    2. explicit connection kwargs::

           create_mysql_fixture(host="localhost", port=3306, user="root",
                                password="...", database="guest3")

       An SSH tunnel is enabled automatically when ``ssh_host`` and
       ``remote_db_host`` are also provided;
    3. default: ``ExtractVar().config`` (reads ``config/config.yaml``).

    Usage in a project's ``conftest.py``::

        from lounger.db_operation import create_mysql_fixture

        mysql_db = create_mysql_fixture(scope="class", user="root",
                                        password="...", database="guest3")

    Then in a test::

        def test_query_sql(self, mysql_db):
            assert isinstance(mysql_db.query_sql("select * from api_user"), list)

    :param scope: pytest fixture scope (default ``"session"``).
    :param config_source: callable or mapping used to resolve the connection
        settings. Defaults to ``ExtractVar().config`` when neither
        ``config_source`` nor explicit kwargs are given.
    :param connection_kwargs: explicit connection kwargs (see item 2 above).
    :return: a pytest fixture named ``mysql_db``.
    """

    @pytest.fixture(scope=scope)
    def mysql_db():
        from lounger.db_operation.resource import build_mysql_resource
        from lounger.utils.variables import ExtractVar

        if config_source is not None:
            resource = build_mysql_resource(config_source)
        elif connection_kwargs:
            resource = _build_mysql_resource_from_kwargs(connection_kwargs)
        else:
            resource = build_mysql_resource(ExtractVar().config)
        with resource as db:
            yield db

    return mysql_db


def create_postgres_fixture(scope: str = "session", **connection_kwargs):
    """
    Create a pytest fixture that provides a PostgreSQL connection.

    :param scope: pytest fixture scope (default ``"session"``).
    :param connection_kwargs: forwarded to
        :meth:`lounger.db_operation.factory.DatabaseFactory.postgres`
        (``host`` / ``port`` / ``database`` / ``user`` / ``password``).
    :return: a pytest fixture named ``postgres_db``.
    """

    @pytest.fixture(scope=scope)
    def postgres_db():
        from lounger.db_operation.factory import DatabaseFactory

        db = DatabaseFactory.postgres(**connection_kwargs)
        try:
            yield db
        finally:
            db.close()

    return postgres_db


def create_mssql_fixture(scope: str = "session", **connection_kwargs):
    """
    Create a pytest fixture that provides a SQL Server connection.

    :param scope: pytest fixture scope (default ``"session"``).
    :param connection_kwargs: forwarded to
        :meth:`lounger.db_operation.factory.DatabaseFactory.mssql`
        (``server`` / ``user`` / ``password`` / ``database`` / ``charset``).
    :return: a pytest fixture named ``mssql_db``.
    """

    @pytest.fixture(scope=scope)
    def mssql_db():
        from lounger.db_operation.factory import DatabaseFactory

        db = DatabaseFactory.mssql(**connection_kwargs)
        try:
            yield db
        finally:
            db.close()

    return mssql_db


def create_sqlite_fixture(scope: str = "session", db_path: str = ":memory:", **connection_kwargs):
    """
    Create a pytest fixture that provides a SQLite connection.

    SQLite needs no external driver, so this fixture is usable in any
    environment (including CI).

    :param scope: pytest fixture scope (default ``"session"``).
    :param db_path: SQLite database file path (default ``":memory:"``).
    :param connection_kwargs: reserved for future SQLite connection options.
    :return: a pytest fixture named ``sqlite_db``.
    """

    @pytest.fixture(scope=scope)
    def sqlite_db():
        from lounger.db_operation.sqlite_db import SQLiteDB

        db = SQLiteDB(db_path=db_path, **connection_kwargs)
        try:
            yield db
        finally:
            db.close()

    return sqlite_db
