from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from distmono.core import Deployable, Project
from distmono.exceptions import BuildNotFoundError
from distmono.util import sh
from functools import cached_property
from marshmallow import Schema, fields, ValidationError
from pathlib import Path
import attr
import boto3
import re
import yaml


class StackerProject(Project):
    def load_env(self, env):
        try:
            return EnvSchema().load(env)
        except ValidationError as e:
            raise ValueError(f'Invalid project env: {e}')


class EnvSchema(Schema):
    namespace = fields.Str(required=True)
    region = fields.Str(required=True)


@attr.s(kw_only=True)
class Stacker:
    work_dir = attr.ib()
    region = attr.ib()
    recreate_failed = attr.ib(default=True)

    def build(self, config, env):
        cmd = ['stacker', 'build', '-r', self.region]

        if self.recreate_failed:
            cmd.append('--recreate-failed')

        with sh.chdir(self.work_dir):
            config_file, env_file = self.generate_input_files(config, env)
            cmd.append(env_file)
            cmd.append(config_file)
            sh.run(cmd)

    def destroy(self, config, env):
        cmd = ['stacker', 'destroy', '-r', self.region, '--force']

        with sh.chdir(self.work_dir):
            config_file, env_file = self.generate_input_files(config, env)
            cmd.append(env_file)
            cmd.append(config_file)
            sh.run(cmd)

    def generate_input_files(self, config, env):
        self.validate_namespace(config, env)
        config_file = Path('config.yaml')
        config_file.write_text(self.get_config_yaml(config))
        env_file = Path('env.yaml')
        env_file.write_text(yaml.dump(env))
        return config_file, env_file

    def get_config_yaml(self, config):
        stacks = [self.get_stack_yaml_obj(s) for s in config.stacks]
        config = {
            'namespace': config.namespace,
            'stacker_bucket': config.stacker_bucket,
            'stacks': stacks,
            'tags': config.tags,
        }
        return yaml.dump(config)

    def get_stack_yaml_obj(self, stack):
        template_file = Path(f'stack.yaml')
        template_file.write_text(stack.template.to_yaml())
        return {
            'name': stack.code,
            'template_path': str(template_file),
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


# TODO: implement fully Deployable methods
class CloudFormation(Deployable):
    def build(self):
        stacker = self.get_stacker(self.context.build_dir)
        stacker.build(self.get_config(), self.context.env)

    def get_stacker(self, work_dir):
        return Stacker(work_dir=work_dir, region=self.get_region())

    def get_config(self):
        return Config(namespace=self.get_namespace(), stacks=[self.get_stack()])

    def get_stack(self):
        return Stack(
            code=self.get_code(),
            template=self.get_template(),
            tags=self.get_tags())

    def get_namespace(self):
        return self.context.env['namespace']

    def get_region(self):
        return self.context.env['region']

    def get_code(self):
        return self.code

    def get_template(self):
        raise NotImplementedError

    def get_tags(self):
        return {}

    def get_build_output(self):
        c = self.get_config()
        stack = self.get_stack()
        stack_name = f'{c.namespace}{c.namespace_delimiter}{stack.code}'
        return self.get_stack_outputs(stack_name)

    def get_stack_outputs(self, stack_name):
        try:
            resp = self.cf.describe_stacks(StackName=stack_name)
        except Exception as e:
            if self.is_stack_does_not_exist_error(e):
                raise BuildNotFoundError(str(e))

            raise

        outputs = resp['Stacks'][0].get('Outputs', [])
        return {o['OutputKey']: o['OutputValue'] for o in outputs}

    @cached_property
    def cf(self):
        config = BotoConfig(region_name=self.get_region())
        return boto3.client('cloudformation', config=config)

    def is_stack_does_not_exist_error(self, e):
        if not isinstance(e, ClientError):
            return False

        m = re.match(r'.*Stack .* does not exist.*', str(e))
        return bool(m)

    def destroy(self):
        stacker = self.get_stacker(self.context.destroy_dir)
        stacker.destroy(self.get_config(), self.context.env)
