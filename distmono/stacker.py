from distmono.core import Deployable
from distmono.util import sh
from functools import cached_property
import attr


@attr.s(kw_only=True)
class Stacker:
    project = attr.ib()
    region = attr.ib()
    recreate_failed = attr.ib(default=True)

    def build(self, config, env):
        cmd = ['stacker', 'build', '-r', self.region]

        if self.recreate_failed:
            cmd.append('--recreate-failed')

        temp_dir, config_file, env_file = self.generate_input_files(config, env)

        with sh.chdir(temp_dir):
            cmd.append(env_file.relative_to(temp_dir))
            cmd.append(config_file.relative_to(temp_dir))
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
        config_file = temp_dir / 'stacker-config.yaml'
        config_file.write_text(self.get_config_yaml(config, temp_dir))
        env_file = temp_dir / 'stacker-env.yaml'
        env_file.write_text(self._to_yaml(env))
        return temp_dir, config_file, env_file

    def get_config_yaml(self, config, temp_dir):
        stacks = [self.get_stack_yaml_obj(s, temp_dir) for s in config.stacks]
        config = {
            'namespace': config.namespace,
            'stacker_bucket': config.stacker_bucket,
            'stacks': stacks,
            'tags': config.tags,
        }
        return self._to_yaml(config)

    def get_stack_yaml_obj(self, stack, temp_dir):
        template_file = temp_dir / f'cfn-{stack.name}.yaml'
        template_file.write_text(stack.template.to_yaml())
        return {
            'name': stack.name,
            'template_path': str(template_file.relative_to(temp_dir)),
            'variables': stack.variables,
            'tags': stack.tags,
        }

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
        import yaml  # lazy import, to speed up CLI
        return yaml.dump(obj)


@attr.s(kw_only=True)
class Config:
    namespace = attr.ib()
    stacker_bucket = attr.ib(default='')
    stacks = attr.ib(default=attr.Factory(list))
    tags = attr.ib(default=attr.Factory(dict))

    # def to_dict(self):
    #     stacks = [s.to_config_dict() for s in self.stacks]
    #     return {
    #         'namespace': self.namespace,
    #         'stacker_bucket': self.stacker_bucket,
    #         'stacks': stacks,
    #         'tags': self.tags,
    #     }


@attr.s(kw_only=True)
class Stack:
    name = attr.ib()
    # blueprint = attr.ib()
    template = attr.ib()  # TODO: validator
    variables = attr.ib(default=attr.Factory(dict))
    tags = attr.ib(default=attr.Factory(dict))

    # def to_config_dict(self):
    #     cls = self.blueprint
    #     class_path = f'{cls.__module__}.{cls.__name__}'
    #     return {
    #         'name': self.name,
    #         'class_path': class_path,
    #         'variables': self.variables,
    #         'tags': self.tags,
    #     }


class StackerDpl(Deployable):
    def build(self):
        stacker = self.get_stacker()
        stacker.build(self.get_stacker_config(), self.context.config)
        # TODO: return output

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
