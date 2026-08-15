from lounger.db_operation.fabric_tunnel import FabricSSHTunnel
from lounger.db_operation.mysql_db import MySQLDB
from lounger.db_operation.resource import (
    MySQLConnectionConfig,
    MySQLResource,
    SSHTunnelConfig,
    build_mysql_resource,
)


class DummyTunnelContext:

    def __init__(self):
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.exited = True


class DummyConnection:
    last_init = None
    last_forward = None
    closed = False
    tunnel_ctx = None

    def __init__(self, host, port, user, connect_kwargs):
        DummyConnection.last_init = {
            "host": host,
            "port": port,
            "user": user,
            "connect_kwargs": connect_kwargs,
        }

    def forward_local(self, local_port, remote_port, remote_host):
        DummyConnection.last_forward = {
            "local_port": local_port,
            "remote_port": remote_port,
            "remote_host": remote_host,
        }
        DummyConnection.tunnel_ctx = DummyTunnelContext()
        return DummyConnection.tunnel_ctx

    def close(self):
        DummyConnection.closed = True


class DummyDBConnection:

    def close(self):
        self.closed = True


def test_fabric_ssh_tunnel_start_and_close(monkeypatch):
    monkeypatch.setattr(FabricSSHTunnel, "_get_connection_cls", staticmethod(lambda: DummyConnection))
    monkeypatch.setattr(FabricSSHTunnel, "_wait_until_ready", lambda self: None)

    tunnel = FabricSSHTunnel(
        ssh_host="jump.example.com",
        ssh_port=22,
        ssh_user="tester",
        ssh_private_key="~/.ssh/id_rsa",
        remote_host="mysql.internal",
        remote_port=3306,
        local_port=23306,
    )

    local_port = tunnel.start()

    assert local_port == 23306
    assert DummyConnection.last_init["host"] == "jump.example.com"
    assert DummyConnection.last_init["connect_kwargs"]["key_filename"].endswith(".ssh/id_rsa")
    assert DummyConnection.last_forward == {
        "local_port": 23306,
        "remote_port": 3306,
        "remote_host": "mysql.internal",
    }
    assert DummyConnection.tunnel_ctx.entered is True

    tunnel.close()

    assert DummyConnection.tunnel_ctx.exited is True
    assert DummyConnection.closed is True


def test_mysql_from_ssh_tunnel(monkeypatch):
    tunnel_state = {"started": False, "closed": False, "kwargs": None}

    class FakeTunnel:
        def __init__(self, **kwargs):
            tunnel_state["kwargs"] = kwargs

        def start(self):
            tunnel_state["started"] = True
            return 23306

        def close(self):
            tunnel_state["closed"] = True

    def fake_connect(**kwargs):
        fake_connect.kwargs = kwargs
        return DummyDBConnection()

    monkeypatch.setattr("lounger.db_operation.resource.FabricSSHTunnel", FakeTunnel)
    monkeypatch.setattr("lounger.db_operation.mysql_db.pymysql.connect", fake_connect)

    db = MySQLDB.from_ssh_tunnel(
        ssh_host="jump.example.com",
        ssh_port=22,
        ssh_user="tester",
        ssh_private_key="~/.ssh/id_rsa",
        ssh_password=None,
        ssh_timeout=15,
        remote_db_host="mysql.internal",
        remote_db_port=3306,
        db_user="dbuser",
        db_password="dbpass",
        db_database="demo",
        db_charset="utf8mb4",
        local_port=13306,
    )

    assert tunnel_state["started"] is True
    assert tunnel_state["kwargs"]["remote_host"] == "mysql.internal"
    assert tunnel_state["kwargs"]["timeout"] == 15
    assert fake_connect.kwargs["host"] == "127.0.0.1"
    assert fake_connect.kwargs["port"] == 23306
    assert fake_connect.kwargs["user"] == "dbuser"
    assert fake_connect.kwargs["database"] == "demo"

    db.close()

    assert tunnel_state["closed"] is True


def test_mysql_from_ssh_tunnel_closes_tunnel_when_db_connect_fails(monkeypatch):
    tunnel_state = {"closed": False}

    class FakeTunnel:
        def __init__(self, **kwargs):
            pass

        def start(self):
            return 23306

        def close(self):
            tunnel_state["closed"] = True

    def fake_connect(**kwargs):
        raise RuntimeError("db connect failed")

    monkeypatch.setattr("lounger.db_operation.resource.FabricSSHTunnel", FakeTunnel)
    monkeypatch.setattr("lounger.db_operation.mysql_db.pymysql.connect", fake_connect)

    try:
        MySQLDB.from_ssh_tunnel(
            ssh_host="jump.example.com",
            ssh_port=22,
            ssh_user="tester",
            remote_db_host="mysql.internal",
            remote_db_port=3306,
            db_user="dbuser",
            db_password="dbpass",
            db_database="demo",
        )
    except RuntimeError as e:
        assert str(e) == "db connect failed"
    else:
        raise AssertionError("Expected db connect failure")

    assert tunnel_state["closed"] is True


def test_mysql_direct_connection(monkeypatch):
    def fake_connect(**kwargs):
        fake_connect.kwargs = kwargs
        return DummyDBConnection()

    monkeypatch.setattr("lounger.db_operation.mysql_db.pymysql.connect", fake_connect)

    db = MySQLDB(
        host="db.example.com",
        port=3307,
        user="dbuser",
        password="dbpass",
        database="demo",
        charset="latin1",
    )

    assert fake_connect.kwargs["host"] == "db.example.com"
    assert fake_connect.kwargs["port"] == 3307
    assert fake_connect.kwargs["charset"] == "latin1"

    db.close()


def test_mysql_resource_direct_connection(monkeypatch):
    def fake_connect(**kwargs):
        fake_connect.kwargs = kwargs
        return DummyDBConnection()

    monkeypatch.setattr("lounger.db_operation.mysql_db.pymysql.connect", fake_connect)

    resource = MySQLResource(
        connection=MySQLConnectionConfig(
            host="db.example.com",
            port=3306,
            user="dbuser",
            password="dbpass",
            database="demo",
        )
    )

    db = resource.connect()

    assert isinstance(db, MySQLDB)
    assert fake_connect.kwargs["host"] == "db.example.com"
    assert fake_connect.kwargs["port"] == 3306

    resource.close()


def test_mysql_resource_with_ssh_tunnel(monkeypatch):
    tunnel_state = {"started": False, "closed": False}

    class FakeTunnel:
        def __init__(self, **kwargs):
            FakeTunnel.kwargs = kwargs

        def start(self):
            tunnel_state["started"] = True
            return 24406

        def close(self):
            tunnel_state["closed"] = True

    def fake_connect(**kwargs):
        fake_connect.kwargs = kwargs
        return DummyDBConnection()

    monkeypatch.setattr("lounger.db_operation.resource.FabricSSHTunnel", FakeTunnel)
    monkeypatch.setattr("lounger.db_operation.mysql_db.pymysql.connect", fake_connect)

    resource = MySQLResource(
        connection=MySQLConnectionConfig(
            host="mysql.internal",
            port=3306,
            user="dbuser",
            password="dbpass",
            database="demo",
        ),
        tunnel=SSHTunnelConfig(
            ssh_host="jump.example.com",
            ssh_port=22,
            ssh_user="tester",
            remote_host="mysql.internal",
            remote_port=3306,
            timeout=15,
            ready_timeout=8.0,
        ),
    )

    with resource as db:
        assert isinstance(db, MySQLDB)
        assert tunnel_state["started"] is True
        assert FakeTunnel.kwargs["timeout"] == 15
        assert FakeTunnel.kwargs["ready_timeout"] == 8.0
        assert fake_connect.kwargs["host"] == "127.0.0.1"
        assert fake_connect.kwargs["port"] == 24406

    assert tunnel_state["closed"] is True


def test_mysql_from_resource(monkeypatch):
    def fake_connect(**kwargs):
        return DummyDBConnection()

    monkeypatch.setattr("lounger.db_operation.mysql_db.pymysql.connect", fake_connect)

    resource = MySQLResource(
        connection=MySQLConnectionConfig(
            host="db.example.com",
            port=3307,
            user="dbuser",
            password="dbpass",
            database="demo",
        )
    )

    db = MySQLDB.from_resource(resource)

    assert isinstance(db, MySQLDB)


def test_build_mysql_resource_from_mapping():
    resource = build_mysql_resource(
        {
            "db_host": "db.example.com",
            "db_port": 3308,
            "db_user": "dbuser",
            "db_password": "dbpass",
            "db_database": "demo",
        },
        use_ssh_tunnel=False,
    )

    assert isinstance(resource, MySQLResource)
    assert resource.connection_config.host == "db.example.com"
    assert resource.connection_config.port == 3308
    assert resource.tunnel_config is None


def test_build_mysql_resource_from_callable_uses_tunnel():
    values = {
        "ssh_host": "jump.example.com",
        "ssh_port": 22,
        "ssh_user": "tester",
        "remote_db_host": "mysql.internal",
        "remote_db_port": 3306,
        "db_user": "dbuser",
        "db_password": "dbpass",
        "db_database": "demo",
        "ssh_timeout": 15,
        "tunnel_ready_timeout": 9.0,
    }

    resource = build_mysql_resource(values.get)

    assert isinstance(resource, MySQLResource)
    assert resource.connection_config.user == "dbuser"
    assert resource.tunnel_config is not None
    assert resource.tunnel_config.ssh_host == "jump.example.com"
    assert resource.tunnel_config.timeout == 15
    assert resource.tunnel_config.ready_timeout == 9.0
