from distmono.core import Deployable, DeploymentGraph, load_project, Project
from distmono.exceptions import CircularDependencyError, ConfigError
from pathlib import Path
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


class TestBuildDependency:
    @pytest.fixture
    def project(self, tmp_path):
        return self.create_project(tmp_path)

    def create_project(self, project_dir):
        class TestProject(Project):
            log = []

            def get_deployables(self):
                return {
                    'a': A,
                    'b1': B1,
                    'b2': B2,
                    'c': C,
                }

            def get_dependencies(self):
                return {
                    'b1': 'a',
                    'b2': 'a',
                    'c': ['b1', 'b2'],
                }

            def get_default_build_target(self):
                return 'c'

        class Common(Deployable):
            def build(self):
                assert self.context.input == self.expected_input
                self.log(type(self).__name__)

            def get_build_output(self):
                return self.build_output

            def destroy(self):
                assert self.context.input == self.expected_input
                self.log('~' + type(self).__name__)

            def log(self, message):
                self.context.project.log.append(message)

        class A(Common):
            expected_input = {}
            build_output = {'apple': 1}

        class B1(Common):
            expected_input = {'a': {'apple': 1}}
            build_output = {'boy': 1}

        class B2(Common):
            expected_input = {'a': {'apple': 1}}
            build_output = {'boy': 2}

        class C(Common):
            expected_input = {
                'b1': {'boy': 1},
                'b2': {'boy': 2},
            }
            build_output = {'cat': 1}

        return TestProject(project_dir=project_dir)

    def test_build(self, project):
        output = project.build()
        assert project.log == ['A', 'B1', 'B2', 'C']
        assert output == {'cat': 1}

    def test_destroy(self, project):
        project.destroy()
        assert project.log == ['~C', '~B1', '~B2', '~A']

    def test_destroy_specific(self, project):
        project.destroy('a')
        assert project.log == ['~C', '~B1', '~B2', '~A']


class TestTempBuildDir:
    @pytest.fixture
    def project(self, tmp_path):
        class TestProject(Project):
            def get_deployables(self):
                return {
                    'all': Deployable,
                    'a': A,
                    'b': B,
                }

            def get_dependencies(self):
                return {
                    'all': ['a', 'b']
                }

            def get_default_build_target(self):
                return 'all'

        class Log(Deployable):
            def build(self):
                self.log_file.write_text(f'{self.name} was here')

            def destroy(self):
                self.log_file.write_text(f'{self.name} is dead')

            @property
            def log_file(self):
                return Path('log')

            @property
            def name(self):
                return type(self).__name__

        class A(Log):
            pass

        class B(Log):
            pass

        return TestProject(project_dir=tmp_path)

    def test_build(self, project):
        project.build()
        build_dir = project.temp_dir / 'build'
        assert (build_dir / 'a/log').read_text() == 'A was here'
        assert (build_dir / 'b/log').read_text() == 'B was here'

    def test_destroy(self, project):
        project.destroy()
        destroy_dir = project.temp_dir / 'destroy'
        assert (destroy_dir / 'a/log').read_text() == 'A is dead'
        assert (destroy_dir / 'b/log').read_text() == 'B is dead'
