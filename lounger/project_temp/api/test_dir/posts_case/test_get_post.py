from lounger.request import expect


def test_get_post(posts_api):
    """Verify fetching a single post."""
    post = posts_api.get_post(1)

    expect(post).to_have_path_value("id", 1)
    expect(post).to_have_path_value("userId", 1)
