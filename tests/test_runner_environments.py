"""Runner environment selection uses the saved YAML with unchanged project fixtures."""
import os
from pathlib import Path

import pytest

from lounger.utils.config_utils import ConfigUtils
from lounger.web_runner.config_document import ConfigDocument
from lounger.web_runner.context import ProjectContext
from lounger.web_runner.manager import RunManager, validate_definition

SOURCE = '''# Saved configuration
environment: develop
environments:
  develop:
    bff: {base_url: https://develop.example.test, auth: develop-token}
  prod:
    bff: {base_url: https://prod.example.test, auth: prod-token}
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith('LOUNGER_'):
            monkeypatch.delenv(key, raising=False)
    root = str(Path(__file__).resolve().parents[1])
    monkeypatch.setenv('PYTHONPATH', root + os.pathsep + os.environ.get('PYTHONPATH', ''))
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/config.yaml').write_text(SOURCE)
    (tmp_path / 'pytest.ini').write_text('[pytest]\n')
    (tmp_path / 'conftest.py').write_text(
        'import pytest\nfrom lounger.utils.config_utils import ConfigUtils\n'
        '@pytest.fixture(scope="session")\ndef environment_config():\n'
        '    cfg = ConfigUtils("config/config.yaml")\n'
        '    return cfg.get_config("environments", cfg.get_config("environment"))\n'
    )
    (tmp_path / 'test_sample.py').write_text(
        'def test_prod(environment_config):\n'
        '    assert environment_config["bff"]["base_url"] == "https://prod.example.test"\n'
        '    assert environment_config["bff"]["auth"] == "prod-token"\n'
    )
    return ProjectContext.create(str(tmp_path))


def test_configutils_selection_keeps_default_and_cache_unchanged(project, monkeypatch):
    path = str(project.root / 'config/config.yaml')
    monkeypatch.setenv('LOUNGER_ENV', 'prod')
    assert ConfigUtils(path).get_config('environment') == 'prod'
    monkeypatch.delenv('LOUNGER_ENV')
    assert ConfigUtils(path).get_config('environment') == 'develop'
    assert Path(path).read_text() == SOURCE


def test_runner_uses_saved_values_and_ignores_old_overrides(project):
    manager = RunManager(project)
    try:
        assert manager.project()['envs'] == ['develop', 'prod']
        assert manager.project()['env'] == 'develop'
        run = manager.start({
            'selection': {'nodeids': ['test_sample.py::test_prod']},
            'options': {'env': 'prod', 'credentials': {'bff.auth': 'obsolete-override'}},
        })
        manager.thread.join(30)
        result = manager.store.run(run['id'])
        assert result['outcome'] == 'passed', result
        assert 'credentials' not in result['request']['options']
        assert (project.root / 'config/config.yaml').read_text() == SOURCE
        assert not (project.data_dir / 'config.overrides.yaml').exists()
    finally:
        manager.close()


def test_task_environment_override_does_not_rewrite_task(project):
    manager = RunManager(project)
    try:
        task = manager.store.save_task(validate_definition({
            'name': 'Configuration smoke',
            'selection': {'nodeids': ['test_sample.py::test_prod']},
            'options': {'env': 'develop'},
        }, task=True))
        run = manager.start(task, task['id'], execution_options={'env': 'prod'})
        manager.thread.join(30)
        assert manager.store.run(run['id'])['outcome'] == 'passed'
        assert manager.store.task(task['id'])['options']['env'] == 'develop'
    finally:
        manager.close()


def test_runner_rejects_unknown_environment_before_execution(project):
    manager = RunManager(project)
    try:
        with pytest.raises(ValueError):
            manager.start({'selection': {'nodeids': ['test_sample.py::test_prod']}, 'options': {'env': 'typo'}})
        assert manager.store.runs()['total'] == 0
    finally:
        manager.close()


def test_environment_convention_is_optional(tmp_path):
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/config.yaml').write_text('custom: {auth: plain-value}\n')
    doc = ConfigDocument.load(tmp_path)
    assert doc.environment() == '' and doc.environments() == []
