from distmono.core import load_project_config, Project
from distmono.exceptions import ConfigError
from textwrap import dedent
import pytest


class TestLoadProjectConfig:
    def load(self, tmp_path, text):
        config_file = tmp_path / 'config.py'
        config_file.write_text(text)
        project = load_project_config(config_file)
        assert isinstance(project, Project)

    def test_valid_config(self, tmp_path):
        self.load(tmp_path, dedent('''\
            from distmono.core import Project

            def get_project():
                project = Project(project_dir='/tmp')
                return project
        '''))

    def test_missing_func(self, tmp_path):
        with pytest.raises(ConfigError, match=r'Missing get_project\(\) in \'.*config\.py\''):
            self.load(tmp_path, dedent('''\
                from distmono.core import Project

                def get_something_else():
                    project = Project(project_dir='/tmp')
                    return project
            '''))

    def test_not_func(self, tmp_path):
        with pytest.raises(ConfigError, match=r'Missing get_project\(\) in \'.*config\.py\''):
            self.load(tmp_path, dedent('''\
                get_project = True
            '''))

    def test_not_return_project(self, tmp_path):
        msg = r'get_project\(\) from \'.*config\.py\' did not return Project instance'

        with pytest.raises(ConfigError, match=msg):
            self.load(tmp_path, dedent('''\
                from distmono.core import Project

                def get_project():
                    return {}
            '''))
