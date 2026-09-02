from pytest_req.assertions import expect

from lounger.commons.load_config import base_url


def test_getting_resource(get):
    """
    Getting a resource

    author: demo
    priority: P1
    tags: smoke, api
    """
    s = get(f"{base_url}/posts/1")
    expect(s).to_be_ok()
    expect(s).to_have_path_value("userId", 1)


def test_creating_resource(post):
    """
    Creating a resource

    author: demo
    priority: P2
    tags: regression
    """
    data = {"title": "foo", "body": "bar", "userId": 1}
    s = post(f'{base_url}/posts', json=data)
    expect(s).to_have_status_code(201)
    json_str = {
        "userId": 1,
        "title": "foo",
        "body": "bar",
    }
    expect(s).to_have_json_matching(json_str)
