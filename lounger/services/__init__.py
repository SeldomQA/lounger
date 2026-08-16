"""
Lounger services layer — reusable, runner-agnostic orchestration.

These modules decouple case discovery / test execution from the web runner
(and any future CLI / platform front-end), per docs/development_plan.md §3.8:

- :mod:`lounger.services.case_discovery` — collect test cases + YAML metadata;
- :mod:`lounger.services.test_execution` — run a set of nodeids via pytest.

The web runner (``lounger.web_runner``) and the platform script
(``myapi/platform_running.py``) share this layer instead of duplicating
collect/execute logic.
"""
