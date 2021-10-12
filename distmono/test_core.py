from distmono.core import DeploymentGraph, load_project, Project
from distmono.exceptions import CircularDependencyError, ConfigError
from textwrap import dedent
import pytest


class TestLoadProject:
    def load(self, tmp_path, text):
        project_file = tmp_path / 'config.py'
        project_file.write_text(text)
        project = load_project(project_file)
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


class TestDeploymentGraph:
    def graph(self, nodes, edges):
        return DeploymentGraph(nodes, edges)

    def test_simple(self):
        g = self.graph(['a', 'b', 'c'], {
            'a': 'b',
            'b': 'c',
        })
        assert g.nodes == ['a', 'b', 'c']
        assert g.edges == [('a', 'b'), ('b', 'c')]
        assert g.sort() == ['a', 'b', 'c']

    def test_cycles(self):
        msg = r'Circular dependency found: .*-\>.*-\>'

        with pytest.raises(CircularDependencyError, match=msg):
            self.graph(['a', 'b', 'c'], {
                'a': 'b',
                'b': 'c',
                'c': 'a',
            })

    def test_dependencies(self):
        g = self.graph(['s3_bucket', 'code', 'lambda1', 'lambda2', 'lambdas'], {
            'code': 's3_bucket',
            'lambda1': 'code',
            'lambda2': 'code',
            'lambdas': ['lambda1', 'lambda2'],
        })
        assert g.successors('lambdas') == ['lambda1', 'lambda2']
        assert g.successors('lambda1') == ['code']
        assert g.successors('code') == ['s3_bucket']
        assert g.successors('s3_bucket') == []

        assert g.predecessors('s3_bucket') == ['code']
        assert g.predecessors('code') == ['lambda1', 'lambda2']
        assert g.predecessors('lambda2') == ['lambdas']
        assert g.predecessors('lambdas') == []

    def test_invalid_edge(self):
        msg = r"Invalid target 'x', must be one of \['d',.*"

        with pytest.raises(ValueError, match=msg):
            self.graph(['d', 'e', 'f'], {'d': 'e', 'x': 'f'})

    def test_invalid_node(self):
        g = self.graph(['x', 'y', 'z'], {})

        with pytest.raises(ValueError, match=r"Invalid target 'u',"):
            g.successors('u')

        with pytest.raises(ValueError, match=r"Invalid target 'v',"):
            g.predecessors('v')
