from lounger import data


@data([2, 4, 6])
def test_params(params):
    print("params", params)
    assert params % 2 == 0


@data([
    (1, "hello"),
    (2, "world"),
])
def test_tuple(params):
    print(params[0], params[1])


@data([
    ["case1", "tom"],
    ["case2", "jack"],
])
def test_list(params):
    print(params[0], params[1])


@data([
    {"username": "admin", "password": "admin123"},
    {"username": "guest", "password": "guest123"},
])
def test_dict(params):
    print(params["username"], params["password"])
