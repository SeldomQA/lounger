"""
requests demo

run test：
> pytest -vs --base-url https://httpbin.org test_request.py
"""
from pytest_req.assertions import expect


def test_put_method(put, base_url):
    """
    test put request
    """
    s = put(f'{base_url}/put', data={'key': 'value'})
    expect(s).to_be_ok()


def test_post_method(post, base_url):
    """
    test post request
    """
    s = post(f'{base_url}/post', data={'key': 'value'})
    expect(s).to_be_ok()


def test_get_method(get, base_url):
    """
    test get request
    """
    payload = {'key1': 'value1', 'key2': 'value2'}
    s = get(f"{base_url}/get", params=payload)
    expect(s).to_be_ok()


def test_delete_method(delete, base_url):
    """
    test delete request
    """
    s = delete(f'{base_url}/delete')
    expect(s).to_be_ok()


def test_patch_method(patch, base_url):
    """
    test patch request
    """
    data = {'key': 'value'}
    s = patch(f"{base_url}/patch", data=data)
    expect(s).to_be_ok()


def test_head_method(head, base_url):
    """
    test head request
    """
    s = head(f"{base_url}/get")
    expect(s).to_be_ok()


def test_options_method(options, base_url):
    """
    test options request
    """
    s = options(f"{base_url}/get")
    expect(s).to_be_ok()
