"""
数据库操作 - 手写 fixture 示例（DatabaseFactory.mssql）

运行前提：安装 pymssql（pip install lounger[db-mssql]）且有可用的 SQL Server。
连接由工厂创建，fixture 结束时在 finally 中 close。
"""
import pytest

pymssql = pytest.importorskip("pymssql", reason="pymssql is not installed")

from lounger.db_operation import DatabaseFactory


@pytest.fixture(scope="function")
def mssql_db():
    """连接 + 数据准备 + 清理（with 退出时自动 close）"""
    with DatabaseFactory.mssql(server="127.0.0.1", user="SA", password="tc@123", database="TestDB") as db:
        db.execute_sql("INSERT INTO users (email, password) VALUES ('test@gmail.com', 'test123') ")
        yield db
        db.delete("users", {"email": "test@gmail.com"})


class TestMSSQL:
    """测试操作MS SQL Server数据库API（fixture 模式）"""

    def test_query_sql(self, mssql_db):
        """测试查询SQL"""
        result = mssql_db.query_sql("select * from users")
        assert isinstance(result, list)

    def test_query_one(self, mssql_db):
        """测试查询SQL一条数据"""
        result = mssql_db.query_one("select * from users")
        assert isinstance(result, tuple)

    def test_execute_sql(self, mssql_db):
        """测试执行SQL"""
        db = mssql_db
        db.execute_sql("INSERT INTO users (email, password) VALUES ('tom@gmail.com', 'tom22') ")
        db.execute_sql("UPDATE users SET password='tom33' WHERE email='tom@gmail.com'")
        db.execute_sql("DELETE FROM users WHERE email = 'tom@gmail.com' ")
        result = db.query_sql("select * from users WHERE email='tom@gmail.com'")
        assert len(result) == 0

    def test_select_sql(self, mssql_db):
        """测试查询SQL"""
        result1 = mssql_db.select(table="users", where={"email": "test@gmail.com"})
        assert result1[0][1] == "test@gmail.com"
        result2 = mssql_db.select(table="users", one=True)
        assert isinstance(result2, tuple)

    def test_delete_sql(self, mssql_db):
        """测试删除SQL"""
        mssql_db.delete(table="users", where={"email": "test@gmail.com"})
        result = mssql_db.query_sql("select * from users WHERE email='test@gmail.com'")
        assert len(result) == 0

    def test_update_sql(self, mssql_db):
        """测试更新SQL"""
        mssql_db.update(table="users", where={"email": "test@gmail.com", }, data={"password": "test22"})
        result = mssql_db.query_sql("select * from users WHERE email='test@gmail.com'")
        assert result[0][2] == 'test22'

    def test_insert_sql(self, mssql_db):
        """测试插入SQL"""
        data = {"email": "jean@gmail.com", "password": "jean11"}
        mssql_db.insert(table="users", data=data)
        result = mssql_db.query_sql("select * from users WHERE email='jean@gmail.com'")
        assert len(result[0]) > 1

    def test_init_table(self, mssql_db):
        """测试批量插入数据"""
        # more table data
        table_data = {
            "users": [
                {"email": "jeannie@gmail.com", "password": "jeannie25"},
                {"email": "joye@gmail.com", "password": "joye26"},
                {"email": "blue@gmail.com", "password": "blue27"},
            ],
        }
        mssql_db.init_table(table_data)
