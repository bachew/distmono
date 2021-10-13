from copy import deepcopy
from distmono.exceptions import CircularDependencyError, ConfigError
from functools import cached_property
from pathlib import Path
import attr
import runpy


class Project:
    def __init__(self, *, project_dir, env=None):
        self.project_dir = Path(project_dir)
        self.env = env

    @property
    def env(self):
        return self._env

    @env.setter
    def env(self, env):
        from marshmallow.exceptions import ValidationError  # slow import

        schema_cls = self.get_env_schema_cls()
        schema = schema_cls()

        try:
            self._env = schema.load(env)
        except ValidationError as e:
            raise ConfigError(f'Invalid env: {e}')

    def get_env_schema_cls(self):
        from marshmallow import Schema, fields  # slow import

        class EnvSchema(Schema):
            namespace = fields.Str(required=True)
            region = fields.Str(required=True)

        return EnvSchema

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

        Builder(self, target).build()

    def destroy(self, target=None):
        Destroyer(self, target).destroy()

    def get_default_build_target(self):
        raise NotImplementedError()

    def create_context(self):
        env = deepcopy(self.env)
        return Context(project=self, env=env)


class Deployable:
    def __init__(self, context):
        self.context = context

    def build(self):
        raise NotImplementedError

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
        self.build_successors_first(self.target)

    def build_successors_first(self, target):
        successors = self.graph.successors(target)

        if successors:
            for successor in successors:
                self.build_successors_first(successor)

        self.build_target_only(target)

    def build_target_only(self, target):
        ctx = self.project.create_context()
        dpl_cls = self.get_deployable_cls(target)
        dpl = dpl_cls(ctx)
        # TODO: don't build if still "fresh"
        dpl.build()
        # TODO: capture build output


class Destroyer(Deployer):
    def destroy(self):
        if self.target:
            self.destroy_predecessors_first(self.target)
        else:
            self.destroy_all()

    def destroy_predecessors_first(self, target):
        predecessors = self.graph.predecessors(target)

        if predecessors:
            for predecessor in predecessors:
                self.destroy_predecessors_first(predecessor)

        self.destroy_one(target)

    def destroy_all(self):
        for target in self.graph.sort():
            self.destroy_one(target)

    def destroy_one(self, target):
        ctx = self.project.create_context()
        dpl_cls = self.get_deployable_cls(target)
        dpl = dpl_cls(ctx)
        dpl.destroy()


@attr.s(kw_only=True)
class Context:
    project = attr.ib()
    env = attr.ib()
    input = attr.ib(default=attr.Factory(dict))


class DeploymentGraph:
    def __init__(self, nodes, edges):
        g = self.nx.DiGraph()
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

        cycles = list(self.nx.simple_cycles(g))

        if cycles:
            path = ' -> '.join(cycles[0])
            msg = f'Circular dependency found: {path}'
            raise CircularDependencyError(msg)

        self.graph = g

    def validate_node(self, node):
        if node not in self.node_set:
            msg = f'Invalid target {node!r}, must be one of {list(self.node_list)!r}'
            raise ValueError(msg)

    @cached_property
    def nx(self):
        import networkx  # slow import
        return networkx

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
        return list(self.nx.topological_sort(self.graph))


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
