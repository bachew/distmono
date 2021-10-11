from distmono.exceptions import ConfigError
from functools import cached_property
from pathlib import Path
import attr
import runpy


@attr.s(kw_only=True)
class Project:
    project_dir = attr.ib()
    components = attr.ib(default=attr.Factory(list))

    @cached_property
    def temp_dir(self):
        return Path(self.project_dir) / 'tmp'

    def compile(self):
        pass

    def clean(self):
        pass

    def build(self):
        pass

    def destroy(self):
        pass


@attr.s(kw_only=True)
class Component:
    name = attr.ib()
    component_dir = attr.ib()
    dependencies = attr.ib(default=attr.Factory(list))

    def compile(self, input):
        return {}

    def clean(self, input):
        pass

    def build(self, input):
        return {}

    def destroy(self, input):
        pass


def load_project_config(config_file):
    mod = runpy.run_path(config_file)
    func = mod.get('get_project')
    config_file = str(config_file)

    if not callable(func):
        raise ConfigError(f'Missing get_project() in {config_file!r}')

    obj = func()

    if not isinstance(obj, Project):
        raise ConfigError(f'get_project() from {config_file!r} did not return Project instance')

    return obj
