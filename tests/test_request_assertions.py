import pytest

from lounger.request import expect


def test_expect_path_type_and_length_assertions():
    resp = {
        "code": 0,
        "data": {
            "carriers": [
                {"carrier_code": "q4848"},
                {"carrier_code": "ups"},
            ]
        },
    }

    expect(resp).to_have_path_value("code", 0)
    expect(resp).to_have_path_be_dict("data")
    expect(resp).to_have_path_be_list("data.carriers")
    expect(resp).to_have_path_length("data.carriers", 2)
    expect(resp).to_have_path_type("data.carriers[0].carrier_code", str)
    expect(resp).to_have_path_not_empty("data.carriers")


def test_expect_path_type_failure_message():
    resp = {"data": {"carriers": []}}

    with pytest.raises(AssertionError, match="Expected path 'data.carriers' to be dict"):
        expect(resp).to_have_path_be_dict("data.carriers")


def test_expect_path_not_empty_failure_message():
    resp = {"data": {"carriers": []}}

    with pytest.raises(AssertionError, match="Expected path 'data.carriers' to be non-empty"):
        expect(resp).to_have_path_not_empty("data.carriers")
