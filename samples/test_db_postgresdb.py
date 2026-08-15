"""
数据库操作 - 手写 fixture 示例（DatabaseFactory.postgres）

运行前提：安装 psycopg2（pip install lounger[db-postgres]）且有可用的 PostgreSQL。
连接由工厂创建，fixture 结束时在 finally 中 close。
"""
import pytest

psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 is not installed")

from lounger.db_operation import DatabaseFactory


@pytest.fixture(scope="function")
def postgres_db():
    """连接 + 数据准备 + 清理（with 退出时自动 close）"""
    with DatabaseFactory.postgres(host="localhost", port=3306, user="dev", password="808801", database="db_user") as db:
        sql = """INSERT INTO
        public.cusm_account (id, name, cn_name, mobile_phone_region, mobile_phone, email, password, status)
        VALUES (DEFAULT, 'test', 'ces', '+86', '13122221111', null, '123456Aq!', 1) """
        db.execute_sql(sql)
        yield db
        db.delete("public.cusm_account", {"name": "test"})


class TestPostgresDB:
    """测试操作PostgreSQL数据库API（fixture 模式）"""

    def test_query_sql(self, postgres_db):
        """测试查询SQL"""
        result = postgres_db.query_sql("select * from public.cusm_account")
        assert isinstance(result, list)

    def test_query_one(self, postgres_db):
        """测试查询SQL一条数据"""
        result = postgres_db.query_one("select * from public.cusm_account")
        assert isinstance(result, dict)

    def test_execute_sql(self, postgres_db):
        """测试执行SQL"""
        db = postgres_db
        db.execute_sql("INSERT INTO public.cusm_account (name, cn_name) VALUES ('tom', 22) ")
        db.execute_sql("UPDATE public.cusm_account SET cn_name=23 WHERE name='tom'")
        db.execute_sql("DELETE FROM public.cusm_account WHERE name = 'tom' ")
        result = db.query_sql("select * from public.cusm_account WHERE name='tom'")
        assert len(result) == 0

    def test_select_sql(self, postgres_db):
        """测试查询SQL"""
        result1 = postgres_db.select(table="public.cusm_account", where={"name": "test"})
        assert result1[0]["name"] == "test"
        result2 = postgres_db.select(table="public.cusm_account", one=True)
        assert isinstance(result2, list)

    def test_delete_sql(self, postgres_db):
        """测试删除SQL"""
        # delete sql
        postgres_db.delete(table="public.cusm_account", where={"name": "test"})
        result = postgres_db.query_sql("select * from public.cusm_account WHERE name='test'")
        assert len(result) == 0

    def test_update_sql(self, postgres_db):
        """测试更新SQL"""
        postgres_db.update(table="public.cusm_account", where={"name": "test", }, data={"cn_name": "22"})
        result = postgres_db.query_sql("select * from public.cusm_account WHERE name='test'")
        assert result[0]["cn_name"] == 22

    def test_insert_sql(self, postgres_db):
        """测试插入SQL"""
        data = {"name": "jean", "cn_name": 11}
        postgres_db.insert(table="public.cusm_account", data=data)
        result = postgres_db.query_sql("select * from public.cusm_account WHERE name='jean'")
        assert len(result[0]) > 1
