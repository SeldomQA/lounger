import os

from lounger.db_operation import SQLiteDB


class TestSQLite3:
    """测试SQLite数据库API"""

    def setup_method(self) -> None:
        """"初始化DB连接"""
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data/db.sqlite3")
        self.db = SQLiteDB(db_path)
        self.db.insert(table="api_user", data={"name": "test", "age": 11})

    def teardown_method(self) -> None:
        self.db.delete("api_user", {"name": "test"})

    def test_query_sql(self):
        """测试查询SQL"""
        result = self.db.query_sql("select * from api_user")
        assert isinstance(result, list)

    def test_query_one(self):
        """测试查询SQL"""
        result = self.db.query_one("select * from api_user")
        assert isinstance(result, tuple)

    def test_execute_sql(self):
        """测试执行SQL"""
        db = self.db
        db.execute_sql("INSERT INTO api_user (name, age) VALUES ('tom', 22) ")
        db.execute_sql("UPDATE api_user SET age=23 WHERE name='tom'")
        db.execute_sql("DELETE FROM api_user WHERE name = 'tom' ")
        result = db.query_sql("select * from api_user WHERE name='tom'")
        assert len(result) == 0

    def test_select_sql(self):
        """测试查询SQL"""
        result = self.db.select(table="api_user", where={"name": "test"})
        assert result[0][1] == "test"
        result = self.db.select(table="api_user", one=True)
        assert isinstance(result, tuple)

    def test_delete_sql(self):
        """测试删除SQL"""
        # delete sql
        self.db.delete(table="api_user", where={"name": "test"})
        result = self.db.query_sql("select * from api_user WHERE name='test'")
        assert len(result) == 0

    def test_update_sql(self):
        """测试更新SQL"""
        self.db.update(table="api_user", where={"name": "test", }, data={"age": "22"})
        result = self.db.query_sql("select * from api_user WHERE name='test'")
        assert result[0][2] == 22

    def test_insert_sql(self):
        """测试插入SQL"""
        data = {"name": "jean", "age": 11}
        self.db.insert(table="api_user", data=data)
        result = self.db.query_sql("select * from api_user WHERE name='jean'")
        assert len(result[0]) > 1

    def test_init_table(self):
        """测试批量插入数据"""
        # more table data
        table_data = {
            "api_user": [  # 表名
                {"name": "jeannie", "age": 25},
                {"name": "joye", "age": 26},
                {"name": "blue", "age": 27},
            ],
        }
        self.db.init_table(table_data)
