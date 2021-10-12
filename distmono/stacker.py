from distmono.core import Deployable
from distmono.util import sh
from functools import cached_property
import attr


@attr.s(kw_only=True)
class Stacker:
    project = attr.ib()
    region = attr.ib()
    recreate_failed = attr.ib(default=True)
    dump = attr.ib(default=False)

    def build(self, config, env):
        cmd = ['stacker', 'build', '-r', self.region]

        if self.recreate_failed:
            cmd.append('--recreate-failed')

        temp_dir, config_file, env_file = self.generate_input_files(config, env)

        with sh.chdir(temp_dir):
            cmd.append(env_file.relative_to(temp_dir))
            cmd.append(config_file.relative_to(temp_dir))

            if self.dump:
                sh.run(cmd + ['--dump', '.'])
                sh.run(['mv', 'stack_templates', 'dump'])  # stack_templates is confusing

            sh.run(cmd)

    def destroy(self, config, env):
        cmd = ['stacker', 'destroy', '-r', self.region, '--force']
        temp_dir, config_file, env_file = self.generate_input_files(config, env)

        with sh.chdir(temp_dir):
            cmd.append(env_file.relative_to(temp_dir))
            cmd.append(config_file.relative_to(temp_dir))
            sh.run(cmd)

    def generate_input_files(self, config, env):
        self.validate_namespace(config, env)
        temp_dir = self.temp_dir / config.namespace
        sh.run(['rm', '-rf', str(temp_dir)])
        temp_dir.mkdir(parents=True, exist_ok=True)
        config_file = temp_dir / 'config.yaml'
        config_file.write_text(self._to_yaml(config.to_dict()))
        env_file = temp_dir / 'env.yaml'
        env_file.write_text(self._to_yaml(env))
        return temp_dir, config_file, env_file

    def validate_namespace(self, config, env):
        ns = 'namespace'

        if ns not in env:
            raise ValueError("'namespace' is mandatory in environment")

        if config.namespace != env[ns]:
            raise ValueError(
                f'Config namespace {config.namespace!r}'
                f' and environment namespace {env[ns]!r} are different'
                f', they should be the same')

    @cached_property
    def temp_dir(self):
        return self.project.temp_dir / 'stacker'

    @cached_property
    def generated_dir(self):
        return self.temp_dir / 'generated'

    def _to_yaml(self, obj):
        import yaml  # lazy import
        return yaml.dump(obj)


@attr.s(kw_only=True)
class Config:
    namespace = attr.ib()
    stacker_bucket = attr.ib(default='')
    # TODO: sys_path
    stacks = attr.ib(default=attr.Factory(list))
    tags = attr.ib(default=attr.Factory(dict))

    def to_dict(self):
        stacks = [s.to_config_dict() for s in self.stacks]
        return {
            'namespace': self.namespace,
            'stacker_bucket': self.stacker_bucket,
            # TODO: sys_path
            'stacks': stacks,
            'tags': self.tags,
        }


@attr.s(kw_only=True)
class Stack:
    name = attr.ib()
    blueprint = attr.ib()
    variables = attr.ib(default=attr.Factory(dict))
    tags = attr.ib(default=attr.Factory(dict))

    def to_config_dict(self):
        cls = self.blueprint
        class_path = f'{cls.__module__}.{cls.__name__}'
        return {
            'name': self.name,
            'class_path': class_path,
            'variables': self.variables,
            'tags': self.tags,
        }


class StackerDpl(Deployable):
    def build(self):
        stacker = self.get_stacker()
        stacker.build(self.get_stacker_config(), self.context.config)

    def destroy(self):
        stacker = self.get_stacker()
        stacker.destroy(self.get_stacker_config(), self.context.config)

    def get_stacker(self):
        return Stacker(project=self.context.project, region=self.get_region())

    def get_stacker_config(self):
        return Config(namespace=self.get_namespace(), stacks=self.get_stacks())

    def get_stacks(self):
        raise NotImplementedError()

    def get_namespace(self):
        return self.context.project.config['namespace']

    def get_region(self):
        return self.context.config['region']
