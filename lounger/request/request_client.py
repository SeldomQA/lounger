import json
import os
from typing import Any, Dict, List, Tuple

import requests
from pytest_req.plugin import Session

from lounger.log import log
from lounger.settings import settings
from lounger.utils import cache


class RequestClient:
    """
    HTTP client wrapper for handling API request
    """

    def __init__(self):
        """
        Initialize the HTTP client.

        The session is created lazily on first use so importing this module
        does not evaluate settings (config changes are picked up without a
        process restart).
        """
        self._session: Session | None = None

    def _get_session(self) -> Session:
        """
        Return a session bound to the *current* base_url.

        The session is recreated when the configured base_url changes, so
        editing config/config.yaml takes effect on the next request.
        """
        base_url = settings.get("base_url")
        if self._session is None or self._session.base_url != base_url:
            self._session = Session(base_url)
        return self._session

    @staticmethod
    def _files_load(files_dict: Dict[str, str]) -> Tuple[Dict[str, Any], List[Any]]:
        """
        Process file upload parameters

        :param files_dict: File upload parameters dictionary
        :return: Tuple of (processed file upload parameters, opened file handles)
        :raises Exception: If file processing fails
        """
        files = {}
        handles = []
        try:
            for file_name, file_path in files_dict.items():
                handle = open(file_path, "rb")
                handles.append(handle)
                files[file_name] = handle
            return files, handles
        except Exception as e:
            # Close any handles opened so far to avoid leaking file descriptors
            for handle in handles:
                handle.close()
            log.error(f"File upload parameters processing failed: {e}")
            raise e

    @staticmethod
    def _read_image(image_path: str) -> bytes:
        """
        Read data from an image file

        :param image_path: Path to the image file
        :return: Binary data from the file
        :raises FileNotFoundError: If the file does not exist
        :raises Exception: If data reading fails for other reasons
        """
        import os
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")
        with open(image_path, "rb") as f:
            return f.read()

    @staticmethod
    def _load_from_path(path: str, is_json: bool = False) -> Any:
        """
        Loads content from a file path.

        :param path: The file path.
        :param is_json: True if the file content should be parsed as JSON.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found for path reference: {path}")

        try:
            with open(path, 'r', encoding='utf-8') as f:
                if is_json:
                    return json.load(f)
                else:
                    return f.read()
        except Exception as e:
            log.error(f"Error reading or parsing file at {path}: {e}")
            raise e

    def send_request(self, **kwargs) -> requests.Response:
        """
        Unified API request handler

        :param kwargs: Parameters for API request
        :return: Response object
        :raises Exception: If API request fails
        :raises NotImplementedError: If HTTP method is not supported
        """
        try:
            if kwargs.get("headers"):
                if isinstance(kwargs.get("headers"), dict):
                    kwargs['headers'] = kwargs.get('headers')
                elif isinstance(kwargs.get("headers"), str):
                    kwargs['headers'] = cache.get(kwargs.get("headers"))
            else:
                # Only set headers if default_headers exists in cache
                kwargs['headers'] = cache.get("default_headers") or {}

            # Process files if present
            opened_files: list[Any] = []
            if "files" in kwargs:
                kwargs["files"], opened_files = self._files_load(kwargs["files"])

            # Add content type for JSON requests
            if kwargs.get("json") is not None:
                kwargs['headers'].setdefault('Content-Type', 'application/json')

            # Use image only if data is not provided and image path exists
            if "image" in kwargs and 'data' not in kwargs:
                image_path = kwargs.get('image')
                if image_path:
                    kwargs['data'] = self._read_image(image_path)
                del kwargs['image']

            # Support GraphQL parameters
            if kwargs.get("json") is not None:
                request_json = kwargs['json']

                if "query_path" in request_json:
                    query_path = request_json.pop("query_path")
                    log.debug(f"Loading GraphQL query from: {query_path}")
                    request_json["query"] = self._load_from_path(query_path, is_json=False)

                if "variables_path" in request_json:
                    variables_path = request_json.pop("variables_path")
                    log.debug(f"Loading variables from: {variables_path}")
                    loaded_vars = self._load_from_path(variables_path, is_json=True)
                    current_vars = request_json.get("variables", {})
                    request_json["variables"] = {**current_vars, **loaded_vars}

                kwargs['json'] = request_json

            # Get method and URL
            method = kwargs.pop("method", "GET").upper()
            url = kwargs.pop("url", "")

            # Send request based on method (session follows the latest base_url)
            session = self._get_session()
            method_handlers = {
                "GET": session.get,
                "POST": session.post,
                "PUT": session.put,
                "DELETE": session.delete,
                "PATCH": session.patch
            }

            if method not in method_handlers:
                # Close any opened upload handles before raising
                for handle in opened_files:
                    handle.close()
                raise NotImplementedError(f"Only supported methods: {', '.join(method_handlers.keys())}")

            try:
                resp = method_handlers[method](url, **kwargs)
            finally:
                # Close the file handles opened for the upload so they are not leaked
                for handle in opened_files:
                    handle.close()

            # Content type handling (commented out but kept for reference)
            # content_type = resp.headers.get("Content-Type", "")

            return resp
        except Exception as e:
            log.error(f"API request failed: {e}")
            raise e


# Create a singleton instance of the request client
request_client = RequestClient()
