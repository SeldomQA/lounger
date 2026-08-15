import pytest
from playwright.sync_api import Page
from autowing.playwright.fixture import create_fixture
from dotenv import load_dotenv


@pytest.fixture
def ai(page):
    """ai fixture"""
    # load .env file config
    load_dotenv()
    ai_fixture = create_fixture()
    return ai_fixture(page)


def test_bing_search_with_ai(page: Page, ai):
    """使用AI执行搜索测试"""
    # 访问必应
    page.goto("https://cn.bing.com")
    
    # 方法1: 分步执行确保回车被触发
    ai.ai_action('在搜索输入框中输入"playwright"')
    page.wait_for_timeout(3000)  # 等待输入完成
    
    ai.ai_action('按下回车键执行搜索')
    page.wait_for_timeout(3000)  # 等待搜索结果加载

    # 使用AI查询搜索结果
    items = ai.ai_query('string[], 搜索结果列表中包含"playwright"相关的标题')

    # 使用AI断言
    assert len(items) > 1
    assert ai.ai_assert('检查搜索结果列表第一条标题是否包含"playwright"字符串')
