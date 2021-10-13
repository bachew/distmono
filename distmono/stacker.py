from distmono.core import Deployable
from distmono.exceptions import BuildNotFoundError
from distmono.util import sh
from functools import cached_property
import attr
import re


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
        config_file = temp_dir / 'config.yaml'
        config_file.write_text(self.get_config_yaml(config, temp_dir))
        env_file = temp_dir / 'env.yaml'
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
        template_file = temp_dir / f'stack-{stack.code}.yaml'
        template_file.write_text(stack.template.to_yaml())
        return {
            'name': stack.code,
            'template_path': str(template_file.relative_to(temp_dir)),
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
    namespace_delimiter = attr.ib(default='-')
    stacker_bucket = attr.ib(default='')
    stacks = attr.ib(default=attr.Factory(list))
    tags = attr.ib(default=attr.Factory(dict))


@attr.s
class Stack:
    code = attr.ib()
    template = attr.ib()  # TODO: validator
    tags = attr.ib(default=attr.Factory(dict), kw_only=True)


class StackerDpl(Deployable):
    def build(self):
        stacker = self.get_stacker()
        stacker.build(self.get_config(), self.context.env)

    def get_build_output(self):
        config = self.get_config()
        ns_delim = config.namespace_delimiter
        ns = config.namespace
        output = {}

        for stack in self.get_stacks():
            stack_name = f'{ns}{ns_delim}{stack.code}'
            output[stack.code] = self.get_stack_outputs(stack_name)

        return output

    def get_stack_outputs(self, stack_name):
        try:
            resp = self.cf.describe_stacks(StackName=stack_name)
        except Exception as e:
            if self.is_stack_does_not_exist_error(e):
                raise BuildNotFoundError(str(e))

            raise

        outputs = resp['Stacks'][0]['Outputs']
        return {o['OutputKey']: o['OutputValue'] for o in outputs}

    @cached_property
    def cf(self):
        # Slow imports
        from botocore.config import Config
        import boto3

        config = Config(region_name=self.get_region())
        return boto3.client('cloudformation', config=config)

    def is_stack_does_not_exist_error(self, e):
        from botocore.exceptions import ClientError  # slow import

        if not isinstance(e, ClientError):
            return False

        m = re.match(r'.*Stack .* does not exist.*', str(e))
        return bool(m)

    def destroy(self):
        stacker = self.get_stacker()
        stacker.destroy(self.get_config(), self.context.env)

    def get_stacker(self):
        return Stacker(project=self.context.project, region=self.get_region())

    def get_config(self):
        return Config(namespace=self.get_namespace(), stacks=self.get_stacks())

    def get_stacks(self):
        raise NotImplementedError

    # TODO: move these out also? If cannot move out, EnvScheme has to move back to core

    def get_namespace(self):
        return self.context.env['namespace']

    def get_region(self):
        return self.context.env['region']
