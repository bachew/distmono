from distmono import (
    CloudFormation,
    Deployable,
    Project,
    Stack,
)
from marshmallow import Schema, fields
from troposphere import (
    GetAtt,
    Output,
    Ref,
    Sub,
    s3,
    Template,
)


class EnvSchema(Schema):
    namespace = fields.Str(required=True)
    region = fields.Str(required=True)


class ApiProject(Project):
    def load_env(self, env):
        schema = EnvSchema()
        return schema.load(env)

    def get_deployables(self):
        return {
            'api-cfn': ApiCfn,
            'function-code': FunctionCode,
            'layer-code': LayerCode,
            'base': Base,
        }

    def get_dependencies(self):
        return {
            'api-cfn': ['function-code', 'layer-code'],
            'function-code': 'base',
            'layer-code': 'base',
        }

    def get_default_build_target(self):
        return 'api-cfn'


class ApiCfn(CloudFormation):
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


class FunctionCode(Deployable):
    def build(self):
        pass  # TODO


class LayerCode(Deployable):
    def build(self):
        pass  # TODO


class Base(CloudFormation):
    def get_stacks(self):
        return [
            Stack('access', self.access_template()),
            Stack('buckets', self.bucket_template()),
        ]

    def access_template(self):
        t = Template()
        # TODO: AppRole, AppPolicy
        return t

    def bucket_template(self):
        ctx = self.context
        t = Template()
        code_bucket = s3.Bucket(
            'CodeBucket',
            BucketName='{namespace}-code'.format(**ctx.env))
        # TODO: access
        t.add_resource(code_bucket)
        t.add_output(Output(f'{code_bucket.title}Name', Value=Ref(code_bucket)))
        # t.add_output(Output(f'{code_bucket.title}Arn', Value=f'arn:aws:s3:::{code_bucket.BucketName}'))
        return t
