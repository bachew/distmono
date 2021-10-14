from distmono import (
    CloudFormation,
    Deployable,
    StackerProject,
    Stack,
)
from troposphere import (
    GetAtt,
    Output,
    Ref,
    Sub,
    s3,
    Template,
)
from functools import cached_property
from pathlib import Path


class ApiProject(StackerProject):
    def get_deployables(self):
        return {
            'api': Api,
            'function-code': FunctionCode,
            'layer-code': LayerCode,
            'base': Base,
        }

    def get_dependencies(self):
        return {
            'api': ['function-code', 'layer-code'],
            'function-code': 'base',
            'layer-code': 'base',
        }

    def get_default_build_target(self):
        return 'api'


class Api(CloudFormation):
    def get_stacks(self):
        return [
            Stack('api', self.api_template()),
            Stack('function', self.function_template()),
        ]

    def api_template(self):
        t = Template()
        # TODO
        t.add_resource(s3.Bucket(
            'DummyBucket',
            BucketName=Sub('${AWS::StackName}-dummy-bucket')))
        return t

    def function_template(self):
        t = Template()
        # TODO
        t.add_resource(s3.Bucket(
            'Function',
            BucketName=Sub('${AWS::StackName}-function')))
        t.add_resource(s3.Bucket(
            'Layer',
            BucketName=Sub('${AWS::StackName}-layer')))
        return t


class Code(Deployable):
    @cached_property
    def code_base_dir(self):
        return Path(__file__).parent / 'api-code'


class FunctionCode(Code):
    def build(self):
        print(f'TODO: build function code from {self.code_dir}')

    @cached_property
    def code_dir(self):
        return self.code_base_dir / 'function'


class LayerCode(Code):
    def build(self):
        print(f'TODO: build layer code from {self.code_dir}')

    @cached_property
    def code_dir(self):
        return self.code_base_dir / 'layer'


class Base(CloudFormation):
    def get_stacks(self):
        return [
            # Stack('access', self.template_access()),
            Stack('buckets', self.template_bucket()),
        ]

    def template_access(self):
        t = Template()
        # TODO: AppRole, AppPolicy
        return t

    def template_bucket(self):
        ctx = self.context
        t = Template()
        self.add_code_bucket(t)
        return t

    def add_code_bucket(self, t):
        ctx = self.context
        bucket = s3.Bucket(
            'CodeBucket',
            BucketName='{namespace}-code'.format(**ctx.env))
        # TODO: access
        t.add_resource(bucket)
        t.add_output(Output(f'{bucket.title}Name', Value=Ref(bucket)))
        # t.add_output(Output(f'{bucket.title}Arn', Value=f'arn:aws:s3:::{bucket.BucketName}'))
