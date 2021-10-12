from copy import deepcopy
from distmono.exceptions import ConfigError
from functools import cached_property
from pathlib import Path
import attr
import runpy


class Project:
    def __init__(self, *, project_dir, config=None):
        self.project_dir = Path(project_dir)
        self.config = config  # TODO: rename this to env to avoid confusion with stacker env

    @property
    def config(self):
        return self._config

    @config.setter
    def config(self, config):
        # TODO: schema and validation, namespace and region are required
        self._config = config

    def get_deployables(self):
        return {}

    @cached_property
    def temp_dir(self):
        return Path(self.project_dir) / 'tmp'

    def build(self, dpl_names=None):
        dpls = self.get_deployables()

        if not dpl_names:
            dpl_names = dpls.keys()

        # TODO: dependency
        for dpl_name in dpl_names:
            ctx = self.create_context()
            dpl_cls = dpls[dpl_name]
            dpl = dpl_cls(ctx)
            dpl.build()

    def create_context(self):
        config = deepcopy(self.config)
        return Context(project=self, config=config)

    def destroy(self, dpl_names=None):
        pass  # TODO


class Deployable:
    def __init__(self, context):
        self.context = context

    def build(self):
        return {}

    def destroy(self):
        pass


@attr.s(kw_only=True)
class Context:
    project = attr.ib()
    config = attr.ib()


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
