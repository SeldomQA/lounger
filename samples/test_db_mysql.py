"""
数据库操作 - 手写 fixture 示例（DatabaseFactory.mysql + MySQLConnectionConfig）

运行前提：本地有可用的 MySQL（host=localhost, database=guest3）。
连接由工厂创建，fixture 结束时在 finally 中 close（含 SSH 隧道）。
"""
import pytest

from lounger.db_operation import DatabaseFactory
from lounger.db_operation.resource import MySQLConnectionConfig


@pytest.fixture(scope="function")
def mysql_db():
    """连接 + 数据准备 + 清理（with 退出时自动 close）"""
    with DatabaseFactory.mysql(connection=MySQLConnectionConfig(
        host="localhost", port=3306, user="root", password="198876", database="guest3",
    )) as db:
        db.execute_sql("INSERT INTO api_user (name, age) VALUES ('test', 11) ")
        yield db
        db.delete("api_user", {"name": "test"})


class TestMySQL:
    """测试操作MySQL数据库API（fixture 模式）"""

    def test_query_sql(self, mysql_db):
        """测试查询SQL"""
        result = mysql_db.query_sql("select * from api_user")
        assert isinstance(result, list)

    def test_query_one(self, mysql_db):
        """测试查询SQL一条数据"""
        result = mysql_db.query_one("select * from api_user")
        assert isinstance(result, dict)

    def test_execute_sql(self, mysql_db):
        """测试执行SQL"""
        db = mysql_db
        db.execute_sql("INSERT INTO api_user (name, age) VALUES ('tom', 22) ")
        db.execute_sql("UPDATE api_user SET age=23 WHERE name='tom'")
        db.execute_sql("DELETE FROM api_user WHERE name = 'tom' ")
        result = db.query_sql("select * from api_user WHERE name='tom'")
        assert len(result) == 0

    def test_select_sql(self, mysql_db):
        """测试查询SQL"""
        result1 = mysql_db.select(table="api_user", where={"name": "test"})
        assert result1[0]["name"], "test"
        result2 = mysql_db.select(table="api_user", one=True)
        assert isinstance(result2, dict)

    def test_delete_sql(self, mysql_db):
        """测试删除SQL"""
        # delete sql
        mysql_db.delete(table="api_user", where={"name": "test"})
        result = mysql_db.query_sql("select * from api_user WHERE name='test'")
        assert len(result) == 0

    def test_update_sql(self, mysql_db):
        """测试更新SQL"""
        mysql_db.update(table="api_user", where={"name": "test", }, data={"age": "22"})
        result = mysql_db.query_sql("select * from api_user WHERE name='test'")
        assert result[0]["age"] == 22

    def test_insert_sql(self, mysql_db):
        """测试插入SQL"""
        data = {"name": "jean", "age": 11}
        mysql_db.insert(table="api_user", data=data)
        result = mysql_db.query_sql("select * from api_user WHERE name='jean'")
        assert len(result[0]) > 1

    def test_init_table(self, mysql_db):
        """测试批量插入数据"""
        # more table data
        table_data = {
            "api_user": [
                {"name": "jeannie", "age": 25},
                {"name": "joye", "age": 26},
                {"name": "blue", "age": 27},
            ],
        }
        mysql_db.init_table(table_data)
