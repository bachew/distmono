from copy import deepcopy
from cached_property import cached_property
from distmono.exceptions import (
    CircularDependencyError,
    ConfigError,
)
from distmono.util import BotoHelper, sh
from marshmallow import Schema, fields, ValidationError
from pathlib import Path
import attr
import hashlib
import networkx as nx
import runpy
import shutil
import yaml


class Project:
    def __init__(self, *, project_dir, env):
        self.project_dir = Path(project_dir).resolve()
        self.env = env

    @property
    def env(self):
        return self._env

    @env.setter
    def env(self, env):
        self._env = self.load_env(env)

    def load_env(self, env):
        try:
            return EnvSchema().load(env)
        except ValidationError as e:
            raise ValueError(f'Invalid project env: {e}')

    def get_deployables(self):
        raise NotImplementedError

    def get_dependencies(self):
        raise NotImplementedError

    def get_default_build_target(self):
        raise NotImplementedError

    @cached_property
    def temp_dir(self):
        return Path(self.project_dir) / 'tmp'

    def build(self, target=None):
        if not target:
            target = self.get_default_build_target()

        return Builder(self, target).build()

    def clear_build_output(self, target):
        self.clear_build_outputs([target])

    def clear_build_outputs(self, targets):
        pass  # TODO

    def destroy(self, target=None):
        Destroyer(self, target).destroy()


class EnvSchema(Schema):
    namespace = fields.Str(required=True)
    region = fields.Str(required=True)


class Deployable:
    def __init__(self, context):
        self.context = context

    def build(self):
        pass

    def get_build_output(self):
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

        with sh.chdir(ctx.build_dir):
            if dpl.is_build_outdated():
                build = True
                sh.print(f'{target}: build outdated')
            else:
                build = False
                sh.print(f'{target}: up-to-date')

            # TODO
            # skip = self.is_target_skipped(target)
            # if skip:
            #     sh.print(f'{target}: skipped')
            #     build = False

            if build:
                dpl.build()

        # TODO: catch error, report error, taking 'skip' into account
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

            # TODO: sh.remove()
            if ctx.build_output_dir.exists():
                shutil.rmtree(ctx.build_output_dir)

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

        try:
            return dpl.get_build_output()
        except Exception:
            raise  # TODO: rethrow with friendlier message


@attr.s(kw_only=True)
class Context:
    project = attr.ib()
    env = attr.ib()
    input = attr.ib(default=attr.Factory(dict))
    build_dir = attr.ib()
    build_output_dir = attr.ib()
    destroy_dir = attr.ib()

    @classmethod
    def create(cls, project, target, input):
        env = deepcopy(project.env)
        tdir = project.temp_dir / 'namespace' / env['namespace']
        return Context(
            project=project,
            env=env,
            input=input,
            build_dir=cls.mkdir(tdir / 'build' / target, clear=True),
            build_output_dir=cls.mkdir(tdir / 'build-output' / target),
            destroy_dir=cls.mkdir(tdir / 'destroy' / target, clear=True),
        )

    @classmethod
    def mkdir(cls, d, clear=False):
        if d.is_file():
            d.unlink()

        if d.is_dir() and clear:
            shutil.rmtree(d)

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


@attr.s(kw_only=True)
class Stacker:
    namespace = attr.ib()
    namespace_delimiter = attr.ib(default='-')
    stacker_bucket = attr.ib(default='')
    stack_code = attr.ib()
    template = attr.ib()
    tags = attr.ib(default=attr.Factory(dict))

    region = attr.ib()
    config_file = attr.ib()
    template_file = attr.ib()

    @config_file.default
    def default_config_file(self):
        return Path('config.yaml')

    @template_file.default
    def default_template_file(self):
        return Path('stack.yaml')

    def generate_input_files(self):
        self.template_file.write_text(self.template.to_yaml())
        config = {
            'namespace': self.namespace,
            'stacker_bucket': self.stacker_bucket,
            'stacks': [
                {
                    'name': self.stack_code,
                    'template_path': str(self.template_file),
                    'tags': self.tags,
                }
            ],
        }
        self.config_file.write_text(yaml.dump(config))

    def build(self):
        cmd = [
            'stacker', 'build',
            '-r', self.region,
            '--recreate-failed',
            str(self.config_file)
        ]
        sh.run(cmd)

    def destroy(self):
        cmd = [
            'stacker', 'destroy',
            '-r', self.region, '--force',
            str(self.config_file)
        ]
        sh.run(cmd)


class Stack(Deployable):
    def build(self):
        self.generate_stacker_files()
        self.stacker.build()

        build_dir = self.context.build_dir

        stack_outputs = self.get_stack_outputs()
        stack_outputs_file = build_dir / self.out_stack_outputs_file.name
        stack_outputs_file.write_text(yaml.dump(stack_outputs))

        stack_outputs_file.replace(self.out_stack_outputs_file)
        self.build_hash_file.replace(self.out_build_hash_file)

    @property
    def build_hash_file(self):
        return self.context.build_dir / 'build-hash.txt'

    def generate_stacker_files(self):
        s = self.stacker
        s.generate_input_files()
        self.build_hash_file.write_text(self.get_build_hash())

    def get_build_hash(self):
        h = hashlib.sha256()
        s = self.stacker
        h.update(s.config_file.read_bytes())
        h.update(s.template_file.read_bytes())
        return h.hexdigest()

    def get_stack_outputs(self):
        s = self.stacker
        stack_name = f'{s.namespace}{s.namespace_delimiter}{s.stack_code}'
        return self.boto.get_stack_outputs(stack_name)

    @cached_property
    def stacker(self):
        return self.get_stacker()

    def get_stacker(self):
        return Stacker(
            namespace=self.get_namespace(),
            stack_code=self.get_stack_code(),
            template=self.get_template(),
            tags=self.get_tags(),
            region=self.get_region(),
        )

    def get_namespace(self):
        return self.context.env['namespace']

    def get_stack_code(self):
        return self.stack_code

    def get_template(self):
        raise NotImplementedError

    def get_tags(self):
        return {}

    def get_region(self):
        return self.context.env['region']

    @cached_property
    def out_stack_outputs_file(self):
        return self.context.build_output_dir / 'stack-outputs.yaml'

    @cached_property
    def out_build_hash_file(self):
        return self.context.build_output_dir / self.build_hash_file.name

    @cached_property
    def boto(self):
        return BotoHelper(region=self.get_region())

    def get_build_output(self):
        return yaml.safe_load(self.out_stack_outputs_file.read_text())

    def is_build_outdated(self):
        try:
            previous_hash = self.out_build_hash_file.read_text()
        except FileNotFoundError:
            return True

        self.generate_stacker_files()
        current_hash = self.build_hash_file.read_text()
        return current_hash != previous_hash

    def destroy(self):
        stacker = self.stacker
        stacker.generate_input_files()
        stacker.destroy()


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
