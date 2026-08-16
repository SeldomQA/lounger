# Lounger API Scaffold

A layered API-testing scaffold: YAML cases + code-style API objects, sharing
the same request path (`lounger.request.RequestClient`) and assertions
(`lounger.request.expect`).

## Layout

```
demo_api/
├── conftest.py            # report title + hook examples (notify / template funcs / execution-chain)
├── test_api.py            # pytest entry that loads YAML cases from datas/
├── pytest.ini
├── config/config.yaml     # base_url / test_project / global_test_config
├── datas/sample/          # YAML test cases (test_sample.yaml)
├── test_dir/              # business test code
│   ├── conftest.py        # fixtures: env_config / posts_api (mysql_db example commented)
│   └── posts_case/        # pytest cases using the API client
├── api/clients/           # API Object layer (HttpRequest + @api)
│   └── posts_api.py
└── support/               # scaffold support (db / notify helpers)
```

## Walkthrough

1. **Install** (from the repo root):

   ```bash
   pip install -e ".[dev]"
   ```

2. **Configure** `config/config.yaml`:

   ```yaml
   base_url: https://jsonplaceholder.typicode.com
   test_project:
     sample: True        # runs datas/sample/
   ```

3. **Run** (from the scaffold directory):

   ```bash
   pytest            # YAML cases from datas/ + pytest cases under test_dir/
   ```

   `test_api.py` collects the configured YAML project (`sample`) and executes
   each `teststeps` block through the case engine.

4. **Extend**:

   - add a YAML case: create `datas/<project>/test_xxx.yaml` and enable the
     project in `test_project`;
   - add an API Object: subclass `HttpRequest` and decorate methods with
     `@api(describe=..., status_code=..., check=..., ret=...)`;
   - add a fixture in `test_dir/conftest.py` (see the commented `mysql_db`
     example — one-liner via `create_mysql_fixture`);
   - hook into request steps via `lounger.plugin_hooks`
     (see commented examples in the root `conftest.py`).

## Reference

- [docs/project_guide.md](../../docs/project_guide.md) — business-project guide
  (three-layer boundary, conftest rules, settings, hooks)
- [docs/plugin_hooks.md](../../docs/plugin_hooks.md) — extension points
- [docs/run_json.md](../../docs/run_json.md) — platform execution protocol
