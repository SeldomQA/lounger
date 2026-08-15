import pytest
from api.clients.posts_api import PostsAPI

from lounger.settings import settings


@pytest.fixture(scope="session")
def env_config() -> dict:
    """Load the shared environment configuration."""
    return {
        "base_url": settings.get("base_url"),
    }


@pytest.fixture()
def posts_api(env_config: dict) -> PostsAPI:
    """Posts API client fixture."""
    return PostsAPI(env_config["base_url"])


# Optional database fixture example:
#
# from lounger.utils.variables import ExtractVar
# from support.db import create_mysql_resource
#
# _extractor = ExtractVar()
#
# @pytest.fixture(scope="session")
# def mysql_db():
#     with create_mysql_resource(_extractor.config) as db:
#         yield db
#
# Recommended one-liner (managed resource, no manual connect/close):
#
# from lounger.db_operation import create_mysql_fixture
#
# mysql_db = create_mysql_fixture(
#     scope="class",
#     host="localhost", port=3306, user="root", password="xxx", database="guest3",
# )
