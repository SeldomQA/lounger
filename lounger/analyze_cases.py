import os
from typing import Any, Dict, List, Optional, Tuple

import pytest
import yaml

from lounger.case_id import case_metadata, encode, extract_step_name, normalize_path
from lounger.commons.load_config import LoadConfig
from lounger.commons.template_engine import validate_template_functions
from lounger.log import log

#: Metadata of the cases loaded by the most recent :func:`load_test_cases` call.
#: The collection subprocess prints it for the runner to persist; it is never
#: written to disk from inside the test session (a ``--collect-only`` run would
#: otherwise overwrite a good manifest with an empty one).
_last_manifest: List[Dict[str, Any]] = []


def get_case_manifest() -> List[Dict[str, Any]]:
    """Return the metadata of the cases loaded by the last :func:`load_test_cases`."""
    return list(_last_manifest)


def reset_case_manifest() -> None:
    """Clear the recorded manifest (primarily for tests)."""
    global _last_manifest
    _last_manifest = []


def relative_case_path(file_path: str, project_root: str) -> str:
    """
    Return ``file_path`` relative to ``project_root``, falling back to its name.

    Case ids embed this path, so it stays stable and platform-independent
    (forward slashes) even when the project is moved.
    """
    try:
        return normalize_path(os.path.relpath(os.path.abspath(file_path), project_root))
    except ValueError:  # different drive on Windows
        return normalize_path(os.path.basename(file_path))


def read_yaml(yaml_path: str, key: Optional[str] = None) -> Any:
    """
    Read a YAML file and return its content.

    :param yaml_path: Path to the YAML file
    :param key: Optional key to extract a specific node
    """
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if key is None:
                return data
            return data.get(key) if isinstance(data, dict) else None
    except Exception as e:
        log.error(f"Error occurred while reading YAML file: {e}")
        return None


def load_yaml_steps(file_path: str) -> List[Dict]:
    """
    Load and extract the first 'teststeps' list from a YAML file.

    :param file_path: Path to the YAML file
    :return: List of step dictionaries
    :raises: RuntimeError if file not found or invalid
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Precondition file not found: {file_path}")

    data = read_yaml(file_path)
    if not data:
        raise RuntimeError(f"Failed to parse or empty YAML file: {file_path}")

    # Find the first 'teststeps' block
    for block in data:
        if isinstance(block, dict) and "teststeps" in block:
            steps = block["teststeps"]
            if isinstance(steps, list):
                return steps
    raise ValueError(f"No 'teststeps' block found in {file_path}")


def load_test_cases() -> List[Tuple[str, List[Dict], str]]:
    """
    Load all test cases from YAML files.

    Each 'teststeps' block in a YAML file is treated as one test case.
    If the first step contains a 'presteps' field with a list of file paths,
    load and merge all steps from those files in order.

    :return: List of tuples (test_name, merged_steps, source_file)
    """
    testcases: List[Tuple[str, List[Dict], str]] = []
    lf = LoadConfig()
    case_paths = lf.get_case_path()

    if not case_paths:
        log.warning("No test case paths configured.")
        return testcases

    project_root = lf.get_project_root()

    for file_path in case_paths:
        file_path = os.path.abspath(file_path)
        # The case id carries the YAML path relative to the project root, so a
        # consumer can recover the source file without guessing (lounger.case_id).
        case_relpath = relative_case_path(file_path, project_root)

        test_data = read_yaml(file_path)
        if not test_data or not isinstance(test_data, list):
            log.warning(f"YAML file is empty or invalid structure: {file_path}")
            continue

        for idx, block in enumerate(test_data):
            if not isinstance(block, dict) or "teststeps" not in block:
                continue

            raw_steps = block["teststeps"]
            if not isinstance(raw_steps, list) or len(raw_steps) == 0:
                log.debug(f"Skipping empty teststeps block in {file_path}")
                continue

            merged_steps = raw_steps
            first_step = raw_steps[0]

            # Check if first step has 'presteps' and it's a list
            if isinstance(first_step, dict) and "presteps" in first_step:
                presteps_files = first_step["presteps"]
                main_steps = raw_steps[1:]

                if not isinstance(presteps_files, list):
                    log.error(f"'presteps' must be a list in {file_path}, got {type(presteps_files).__name__}")
                    continue

                if len(presteps_files) == 0:
                    log.debug(f"No presteps files specified in {file_path}")
                    merged_steps = main_steps
                else:
                    presteps: Optional[List[Dict]] = []
                    log.info(f"🔁 Loading pre-steps: {presteps_files}")

                    # Load each pre-steps file in order
                    for rel_path in presteps_files:
                        if not isinstance(rel_path, str):
                            log.error(
                                f"Invalid presteps item, expected string but got {type(rel_path).__name__}: {rel_path}")
                            presteps = None
                            break

                        full_path = os.path.normpath(os.path.join(project_root, rel_path))
                        try:
                            steps = load_yaml_steps(full_path)
                            assert presteps is not None
                            presteps.extend(steps)
                            log.debug(f"✔️ Loaded {len(steps)} step(s) from '{rel_path}'")
                        except Exception as e:
                            log.error(f"❌ Failed to load pre-steps file '{rel_path}': {str(e)}")
                            presteps = None
                            break  # Stop on first failure

                    if presteps is not None:
                        merged_steps = presteps + main_steps
                        log.info(f"✅ Merged {len(presteps)} pre-step(s) into test case")
                    else:
                        continue  # Skip this test case due to load failure

            # Generate the case id from the first step after merge. The format
            # lives in lounger.case_id so this producer and the consumers
            # (case_discovery, the Web Runner tree) cannot drift apart.
            first_step_after_merge = merged_steps[0] if merged_steps else None
            test_name = encode(case_relpath, idx + 1, extract_step_name(first_step_after_merge))

            # Fail (or warn) at collection time instead of injecting `null` at
            # run time when a case references an unregistered template function.
            validate_template_functions(merged_steps, f"{case_relpath} case_{idx + 1}")

            testcases.append((test_name, merged_steps, file_path))

    # Record the source-file metadata of what was loaded. Consumers (the runner's
    # case tree, the platform API) read it from here instead of re-deriving it
    # from node IDs, so attribution stays exact.
    global _last_manifest
    _last_manifest = [
        case_metadata(relative_case_path(source_file, project_root), index + 1, steps[0] if steps else None)
        for index, (_name, steps, source_file) in enumerate(testcases)
    ]

    # Final summary
    if not testcases:
        log.warning("No valid test cases loaded from YAML files.")
    else:
        log.info(f"✅ Successfully loaded {len(testcases)} test case(s)")

    return testcases


def load_teststeps():
    """
    Pytest decorator factory to parametrize test cases.
    Loads test cases and returns pytest.mark.parametrize with proper args and IDs.
    """
    info = """
╭─ YAML API Testing ────────────────────────────────────────────────────────────────────╮
│- teststeps:                                                                           │
│    - step: Getting a resource                                                         │ 
│      request:                                                                         │  
│        method: GET                                                                    │ 
│        url: /posts/1                                                                  │
│      validate:                                                                        │
│        equal:                                                                         │
│          - [ "status_code", 200 ]                                                     │
╰───────────────────────────────────────────────────────────────────────────────────────╯
"""
    log.info(info)
    cases = load_test_cases()
    parametrized_cases: List[Dict[str, Any]] = [
        {"name": name, "steps": steps, "file": file_path}
        for name, steps, file_path in cases
    ]

    return pytest.mark.parametrize(
        "teststeps",
        parametrized_cases,
        ids=[case["name"] for case in parametrized_cases]
    )
