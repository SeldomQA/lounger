import copy
from typing import Any, Dict, Optional

from pytest_req.utils.jmespath import jmespath

from lounger.log import log
from lounger.utils.cache import cache


def _save_extracted_values(key: str, result: Any) -> None:
    """
    Save extracted values, handling both single values and lists
    
    :param key: Variable name
    :param result: Extracted value or list of values
    """
    if isinstance(result, list):
        for i, item in enumerate(result):
            cache.set({f"{key}_{i}": item})
    else:
        cache.set({key: result})


def extract_var(resp: Any, expr_or_data: Optional[Dict[str, str]]) -> None:
    """
    Save API association intermediate variables

    :param resp: API response object
    :param expr_or_data: Extraction parameters
    """
    prepared_resp = copy.deepcopy(resp)
    if prepared_resp is None or expr_or_data is None:
        return None

    try:
        resp_json = prepared_resp.json()
    except ValueError as e:
        log.error(f"The response is not a valid JSON: {e}")
        return None

    if isinstance(resp_json, dict) or isinstance(resp_json, list):
        for key, expr in expr_or_data.items():
            try:
                result = jmespath(resp_json, expr)
                if result is None:
                    log.warning(f"Extracted variable is None: name={key}, expression={expr}")
                    continue
                # Save the extracted value
                _save_extracted_values(key, result)
            except Exception as e:
                log.error(f"Failed to extract or save variable '{key}' with expression '{expr}': {e}")
                continue

    return None
