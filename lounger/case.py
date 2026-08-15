import inspect
import os
import runpy
import sys
import time
from pathlib import Path
from typing import Any, Dict

from lounger.commons.assert_result import api_validate
from lounger.commons.extract import extract_var
from lounger.commons.model import verify_model
from lounger.commons.template_engine import template_replace
from lounger.log import log
from lounger.plugin_hooks import (
    run_after_execute_step,
    run_before_execute_step,
    run_on_execute_step_error,
)


def execute_script(this_file_path: Path, pre_script: str):
    """
    Execute the hook function dynamically.
    :param this_file_path: function name
    :param pre_script: hook file name
    """
    this_file_dir = this_file_path.parent
    sys.path.insert(0, str(this_file_dir))

    _scrip_path = None
    for root, _, files in os.walk(this_file_dir, topdown=False):
        for _file in files:
            if _file == pre_script:
                _scrip_path = os.path.join(root, _file)
                break
        else:
            continue
        break

    # running pre script
    log.info(f"🐍 Executing script {_scrip_path}")
    runpy.run_path(_scrip_path)


def execute_step(case_step: Dict[str, Any]) -> None:
    """
    Execute a test case step.

    Runs the execution-chain hooks (see ``lounger.plugin_hooks``):

    1. ``run_before_execute_step(case_step)`` — before the request is sent;
    2. the step is dispatched (request / centrifuge);
    3. on failure ``run_on_execute_step_error(case_step, exc)`` fires and the
       exception is re-raised;
    4. ``run_after_execute_step(case_step, resp)`` — after a successful step.

    :param case_step: Test case step
    :return: None
    :raises Exception: If test case execution fails
    """
    step_name = case_step.get('name')
    log.info(f"Executing test step: {step_name}")

    # Execution-chain hook: before the request is sent
    run_before_execute_step(case_step)

    # Verify model and replace templates
    validated_case = verify_model(case_step)
    processed_case = template_replace(validated_case)

    try:
        if case_step.get("centrifuge"):
            # New Send centrifuge
            from lounger.centrifuge import centrifuge_manager
            resp = centrifuge_manager.send_centrifuge(**processed_case["centrifuge"])
        elif case_step.get("request"):
            # Send request
            from lounger.request import request_client
            resp = request_client.send_request(**processed_case["request"])
        else:
            raise TypeError("Currently, only WebSocket and HTTP (request) protocols are supported.")
    except Exception as exc:
        # Execution-chain hook: failure callback
        run_on_execute_step_error(case_step, exc)
        raise

    # Execution-chain hook: after the request completed successfully
    run_after_execute_step(case_step, resp)

    # Sleep if a sleep duration is specified
    if sleep_sec := case_step.get("sleep"):
        time.sleep(sleep_sec)
    # Code for variable extraction and API validation is commented out
    extract_var(resp, processed_case.get("extract"))
    api_validate(resp, processed_case.get("validate"))


def execute_teststeps(teststeps: Dict) -> None:
    """
    execute the test steps
    :param teststeps
    """
    test_name = teststeps["name"]
    test_steps = teststeps["steps"]
    file_path = teststeps["file"]

    log.info(f"✅ Starting test case: {test_name}")
    log.info(f"📁 Source file: {file_path}")
    log.info(f"🔧 Contains {len(test_steps)} step(s)")

    stack_t = inspect.stack()
    ins = inspect.getframeinfo(stack_t[1][0])
    this_file_path = Path(ins.filename).resolve()

    for i, step in enumerate(test_steps):
        step_name = step.get("name", None)
        if step_name is None:
            step_name = step.get("step", f"step_{i + 1}")
        log.info(f"🔹 Executing step {i + 1}/{len(test_steps)}: {step_name}")
        # execute pre script
        if step.get('prescript'):
            execute_script(this_file_path, step.get('prescript'))
        execute_step(step)
