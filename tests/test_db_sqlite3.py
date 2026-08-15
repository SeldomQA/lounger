"""
数据库操作 - 手写 fixture 示例（SQLiteDB）

SQLite 使用标准库驱动，无需安装额外依赖，可在任意环境（含 CI）运行。
连接由 SQLiteDB 创建，fixture 结束时在 finally 中 close。
"""
import os

import pytest

from lounger.db_operation import SQLiteDB


@pytest.fixture(scope="function")
def sqlite_db():
    """连接 + 数据准备 + 清理（with 退出时自动 close）"""
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data/db.sqlite3")
    with SQLiteDB(db_path) as db:
        db.insert(table="api_user", data={"name": "test", "age": 11})
        yield db
        db.delete("api_user", {"name": "test"})


class TestSQLite3:
    """测试SQLite数据库API（fixture 模式）"""

    def test_query_sql(self, sqlite_db):
        """测试查询SQL"""
        result = sqlite_db.query_sql("select * from api_user")
        assert isinstance(result, list)

    def test_query_one(self, sqlite_db):
        """测试查询SQL"""
        result = sqlite_db.query_one("select * from api_user")
        assert isinstance(result, tuple)

    def test_execute_sql(self, sqlite_db):
        """测试执行SQL"""
        db = sqlite_db
        db.execute_sql("INSERT INTO api_user (name, age) VALUES ('tom', 22) ")
        db.execute_sql("UPDATE api_user SET age=23 WHERE name='tom'")
        db.execute_sql("DELETE FROM api_user WHERE name = 'tom' ")
        result = db.query_sql("select * from api_user WHERE name='tom'")
        assert len(result) == 0

    def test_select_sql(self, sqlite_db):
        """测试查询SQL"""
        result = sqlite_db.select(table="api_user", where={"name": "test"})
        assert result[0][1] == "test"
        result = sqlite_db.select(table="api_user", one=True)
        assert isinstance(result, tuple)

    def test_delete_sql(self, sqlite_db):
        """测试删除SQL"""
        # delete sql
        sqlite_db.delete(table="api_user", where={"name": "test"})
        result = sqlite_db.query_sql("select * from api_user WHERE name='test'")
        assert len(result) == 0

    def test_update_sql(self, sqlite_db):
        """测试更新SQL"""
        sqlite_db.update(table="api_user", where={"name": "test", }, data={"age": "22"})
        result = sqlite_db.query_sql("select * from api_user WHERE name='test'")
        assert result[0][2] == 22

    def test_insert_sql(self, sqlite_db):
        """测试插入SQL"""
        data = {"name": "jean", "age": 11}
        sqlite_db.insert(table="api_user", data=data)
        result = sqlite_db.query_sql("select * from api_user WHERE name='jean'")
        assert len(result[0]) > 1

    def test_init_table(self, sqlite_db):
        """测试批量插入数据"""
        # more table data
        table_data = {
            "api_user": [  # 表名
                {"name": "jeannie", "age": 25},
                {"name": "joye", "age": 26},
                {"name": "blue", "age": 27},
            ],
        }
        sqlite_db.init_table(table_data)
