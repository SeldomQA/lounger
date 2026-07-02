"""
Lounger response assertions.
"""
from __future__ import annotations

import json
from typing import Any

import requests
from pytest_req.assertions import Expect as PytestReqExpect
from pytest_req.utils.jmespath import jmespath

from lounger.log import log


class Expect(PytestReqExpect):
    """
    Extend pytest-req assertions with a few higher-level response assertions.
    """

    def _json_body(self) -> Any:
        if isinstance(self.response, requests.Response):
            try:
                return self.response.json()
            except json.JSONDecodeError as e:
                raise AssertionError("Response does not contain valid JSON") from e
        return self.response

    def _path_value(self, path: str) -> Any:
        return jmespath(self._json_body(), path)

    def to_have_path_type(self, path: str, expected_type: type) -> None:
        """
        Assert the value at path is an instance of the expected type.
        """
        actual = self._path_value(path)
        log.info(f"👀 assert path type -> {path} is {expected_type.__name__}.")
        assert isinstance(actual, expected_type), (
            f"Expected path '{path}' to be {expected_type.__name__}, "
            f"but got {type(actual).__name__}: {actual}"
        )

    def to_have_path_length(self, path: str, expected_length: int) -> None:
        """
        Assert the value at path has the expected length.
        """
        actual = self._path_value(path)
        log.info(f"👀 assert path length -> {path} == {expected_length}.")
        try:
            actual_length = len(actual)
        except TypeError as e:
            raise AssertionError(f"Expected path '{path}' to be countable, but got {type(actual).__name__}") from e
        assert actual_length == expected_length, (
            f"Expected path '{path}' length {expected_length}, but got {actual_length}: {actual}"
        )

    def to_have_path_not_empty(self, path: str) -> None:
        """
        Assert the value at path is not empty.
        """
        actual = self._path_value(path)
        log.info(f"👀 assert path not empty -> {path}.")
        assert actual, f"Expected path '{path}' to be non-empty, but got {actual}"

    def to_have_path_be_list(self, path: str) -> None:
        """
        Assert the value at path is a list.
        """
        self.to_have_path_type(path, list)

    def to_have_path_be_dict(self, path: str) -> None:
        """
        Assert the value at path is a dict.
        """
        self.to_have_path_type(path, dict)

    def to_have_path_be_str(self, path: str) -> None:
        """
        Assert the value at path is a string.
        """
        self.to_have_path_type(path, str)

    def to_have_path_be_int(self, path: str) -> None:
        """
        Assert the value at path is an int.
        """
        self.to_have_path_type(path, int)


def expect(response: Any) -> Expect:
    """
    Lounger expect entrypoint.
    """
    return Expect(response)
