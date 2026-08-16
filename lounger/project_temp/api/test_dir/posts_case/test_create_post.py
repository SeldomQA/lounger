import pytest

from lounger.request import expect
from lounger.utils.resource_loader import resource_file


@pytest.fixture(scope="module")
def create_post_payload() -> dict:
    """Load the JSON payload used for post creation."""
    payload = resource_file("create_post_payload.json")
    assert isinstance(payload, dict), "create_post_payload.json must contain a JSON object"
    return payload


def test_create_post(posts_api, create_post_payload: dict):
    """Verify creating a post."""
    post = posts_api.create_post(create_post_payload)

    expect(post).to_have_path_value("title", create_post_payload["title"])
    expect(post).to_have_path_value("body", create_post_payload["body"])
    expect(post).to_have_path_value("userId", create_post_payload["userId"])
