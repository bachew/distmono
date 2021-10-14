from copy import deepcopy
from distmono.exceptions import CircularDependencyError, ConfigError
from distmono.util import sh
from functools import cached_property
from pathlib import Path
import attr
import networkx as nx
import runpy


class Project:
    def __init__(self, *, project_dir, env=None):
        self.project_dir = Path(project_dir)

        if env is None:
            env = {}

        self.env = env

    @property
    def env(self):
        return self._env

    @env.setter
    def env(self, env):
        self._env = self.load_env(env)

    def load_env(self, env):
        if not isinstance(env, dict):
            raise ValueError('Invalid project env, it must be a dict')

        return env

    def get_deployables(self):
        raise NotImplementedError

    def get_dependencies(self):
        raise NotImplementedError

    @cached_property
    def temp_dir(self):
        return Path(self.project_dir) / 'tmp'

    def build(self, target=None):
        if not target:
            target = self.get_default_build_target()

        return Builder(self, target).build()

    def destroy(self, target=None):
        Destroyer(self, target).destroy()

    def get_default_build_target(self):
        raise NotImplementedError


class Deployable:
    def __init__(self, context):
        self.context = context

    def build(self):
        pass

    def get_build_output(self):
        '''
        Returns the result of previous build, throws BuildNotFoundError if it
        wasn't built before.
        '''
        return {}

    def is_build_outdated(self):
        return True

    def destroy(self):
        pass


class Deployer:
    def __init__(self, project, target):
        self.project = project
        self.target = target

    @cached_property
    def deployables(self):
        return self.project.get_deployables()

    def get_deployable_cls(self, target):
        return self.deployables[target]

    @cached_property
    def graph(self):
        nodes = list(self.deployables.keys())
        edges = self.project.get_dependencies()
        return DeploymentGraph(nodes, edges)


class Builder(Deployer):
    def build(self):
        builds = {}
        return self.build_successors_first(self.target, builds)

    def build_successors_first(self, target, builds):
        input = {}

        for successor in self.graph.successors(target):
            output = self.build_successors_first(successor, builds)
            input[successor] = output

        if target not in builds:
            builds[target] = self.build_target_only(target, input)

        return builds[target]

    def build_target_only(self, target, input):
        ctx = Context.create(self.project, target, input)
        dpl_cls = self.get_deployable_cls(target)
        dpl = dpl_cls(ctx)

        if dpl.is_build_outdated():  # TODO: option to force build all or some targets
            with sh.chdir(ctx.build_dir):
                dpl.build()

        output = dpl.get_build_output()
        # TODO: validate/filter
        return output


class Destroyer(Deployer):
    def destroy(self):
        if self.target:
            self.destroyed = set()
            self.destroy_predecessors_first(self.target)
        else:
            self.destroy_all()

    def destroy_predecessors_first(self, target):
        predecessors = self.graph.predecessors(target)

        for predecessor in predecessors:
            self.destroy_predecessors_first(predecessor)

        if target not in self.destroyed:
            self.destroy_one(target)
            self.destroyed.add(target)

    def destroy_all(self):
        for target in self.graph.sort():
            self.destroy_one(target)

    def destroy_one(self, target):
        input = self.get_successor_outputs(target)
        ctx = Context.create(self.project, target, input)
        dpl_cls = self.get_deployable_cls(target)
        dpl = dpl_cls(ctx)

        with sh.chdir(ctx.destroy_dir):
            dpl.destroy()

    def get_successor_outputs(self, target):
        outputs = {}

        for successor in self.graph.successors(target):
            outputs[successor] = self.get_build_output(successor)

        return outputs

    def get_build_output(self, target):
        input = self.get_successor_outputs(target)
        ctx = Context.create(self.project, target, input)
        dpl_cls = self.get_deployable_cls(target)
        dpl = dpl_cls(ctx)
        # TODO: rethrow BuildNotFoundError with elaboration
        return dpl.get_build_output()


@attr.s(kw_only=True)
class Context:
    project = attr.ib()
    env = attr.ib()
    input = attr.ib(default=attr.Factory(dict))
    build_dir = attr.ib()
    build_output_dir = attr.ib()
    destroy_dir = attr.ib()
    destroy_output_dir = attr.ib()

    @classmethod
    def create(cls, project, target, input):
        env = deepcopy(project.env)
        tdir = project.temp_dir
        return Context(
            project=project,
            env=env,
            input=input,
            build_dir=cls._mkdir(tdir / 'build' / target),
            build_output_dir=cls._mkdir(tdir / 'build-output' / target),
            destroy_dir=cls._mkdir(tdir / 'destroy' / target),
            destroy_output_dir=cls._mkdir(tdir / 'destroy-output' / target),
        )

    @classmethod
    def _mkdir(cls, d):
        d.mkdir(parents=True, exist_ok=True)
        return d


class DeploymentGraph:
    def __init__(self, nodes, edges):
        g = nx.DiGraph()
        self.node_set = set()
        self.node_list = []

        for node in nodes:
            g.add_node(node)

            if node not in self.node_set:
                self.node_set.add(node)
                self.node_list.append(node)

        for a, b in edges.items():
            self.validate_node(a)

            if not isinstance(b, (list, tuple)):
                b = [b]

            for b_item in b:
                self.validate_node(b_item)
                g.add_edge(a, b_item)

        cycles = list(nx.simple_cycles(g))

        if cycles:
            path = ' -> '.join(cycles[0])
            msg = f'Circular dependency found: {path}'
            raise CircularDependencyError(msg)

        self.graph = g

    def validate_node(self, node):
        if node not in self.node_set:
            msg = f'Invalid target {node!r}, must be one of {list(self.node_list)!r}'
            raise ValueError(msg)

    @property
    def nodes(self):
        return list(self.graph.nodes())

    @property
    def edges(self):
        return list(self.graph.edges())

    def successors(self, node):
        self.validate_node(node)
        return list(self.graph.successors(node))

    def predecessors(self, node):
        self.validate_node(node)
        return list(self.graph.predecessors(node))

    def sort(self):
        return list(nx.topological_sort(self.graph))


def load_project(filename):
    mod = runpy.run_path(filename)
    func = mod.get('get_project')
    filename = str(filename)

    if not callable(func):
        raise ConfigError(f'Missing get_project() in {filename!r}')

    obj = func()

    if not isinstance(obj, Project):
        raise ConfigError(f'get_project() from {filename!r} did not return Project instance')

    return obj
