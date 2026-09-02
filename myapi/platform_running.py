"""
function: 该脚本支持平台化运行 (docs/development_plan.md §F1)
参考：https://seldomqa.github.io/platform/platform.html

全流程：收集（含 tags/author/priority）→ 按序执行 → 结果回传（文件 + 回调 URL）。

运行（在 myapi 目录下）：
    python platform_running.py
"""

import json
import os

import pytest

from lounger.log import log
from lounger.services.case_discovery import discover_cases

#: 回调 URL（平台入库接口）。空则跳过回传。
RESULT_CALLBACK_URL = os.environ.get("LOUNGER_RESULT_CALLBACK", "")


def collected_cases(collect_dir: str, output_path: str):
    """
    收集测试用例保存到指定文件（tags/author/priority 随用例输出）。
    """
    # 统一走 lounger.services.case_discovery（web_runner / CLI / 平台共用）
    cases = discover_cases(collect_dir)
    if isinstance(cases, dict) and "error" in cases:
        log.error(f"Collect failed: {cases['error']}")
        raise RuntimeError(cases["error"])

    # Write to JSON file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cases, f, indent=4, ensure_ascii=False)

    log.info(f"Test cases collected and saved to: {output_path} ({len(cases)} cases)")


def running_cases(execute_path: str):
    """
    执行收集到的测试用例，并生成 junit + json 结果、回传平台。
    """
    log.info(f"✓ Executing test cases from: {execute_path}")

    result_file = "./reports/result.json"
    cmd = [
        "--run-json",
        execute_path,
        "--junit-xml=./reports/result.xml",
        f"--result-file={result_file}",
        "-W",
        "ignore::pytest.PytestAssertRewriteWarning",
    ]
    if RESULT_CALLBACK_URL:
        cmd.append(f"--result-callback={RESULT_CALLBACK_URL}")

    exit_code = pytest.main(cmd)

    if os.path.exists(result_file):
        with open(result_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
        summary = payload.get("summary", {})
        log.info(
            f"📦 Results: {summary.get('passed', 0)} passed, "
            f"{summary.get('failed', 0)} failed, "
            f"{summary.get('skipped', 0)} skipped "
            f"(total {summary.get('total', 0)})"
        )
    return exit_code


if __name__ == "__main__":
    cases_path = "./collected_cases/test_cases_info.json"

    # step1: 收集当前项目下的测试用例（含 tags/author/priority）
    collected_cases(collect_dir="./", output_path=cases_path)

    # step2: 执行收集到的测试用例，结果回传平台
    running_cases(execute_path=cases_path)
