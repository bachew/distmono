from distmono import (
    CloudFormation,
    Deployable,
    StackerProject,
)
from troposphere import (
    GetAtt,
    iam,
    Output,
    Ref,
    s3,
    Sub,
    Template,
)
from functools import cached_property
from pathlib import Path
from awacs.aws import Action, Allow, PolicyDocument, Principal, Statement
from awacs.sts import AssumeRole


class ApiProject(StackerProject):
    def get_deployables(self):
        return {
            'api-stack': ApiStack,
            'function-code': FunctionCode,
            'layer-code': LayerCode,
            'buckets-stack': BucketsStack,
            'access-stack': AccessStack,
        }

    def get_dependencies(self):
        return {
            'api-stack': ['function-code', 'layer-code'],
            'function-code': 'buckets-stack',
            'layer-code': 'buckets-stack',
            'buckets-stack': 'access-stack',
        }

    def get_default_build_target(self):
        return 'api-stack'


class ApiStack(CloudFormation):
    code = 'api'

    def get_template(self):
        t = Template()
        # TODO
        t.add_resource(s3.Bucket(
            'DummyBucket',
            BucketName=Sub('${AWS::StackName}-dummy-bucket')))
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


class AccessStack(CloudFormation):
    code = 'access'

    def get_template(self):
        t = Template()
        app_policy = self.add_app_policy(t)
        self.add_app_role(t, app_policy)
        return t

    def add_app_policy(self, t):
        policy = iam.ManagedPolicy(
            'AppPolicy',
            PolicyDocument=self.policy_document([
                Statement(
                    Effect=Allow,
                    Action=[Action('lambda', 'InvokeFunction')],
                    Resource=['*'],  # TODO: narrow down
                ),
                Statement(
                    Effect=Allow,
                    Action=[Action('s3', '*')],
                    Resource=['*'],  # TODO: narrow down
                )
            ])
        )
        return t.add_resource(policy)

    def add_app_role(self, t, app_policy):
        role = iam.Role(
            'AppRole',
            RoleName='app',
            AssumeRolePolicyDocument=self.policy_document([
                Statement(
                    Effect=Allow,
                    Action=[AssumeRole],
                    Principal=Principal('Service', [
                        'lambda.amazonaws.com',
                        'apigateway.amazonaws.com',
                        # 'firehose.amazonaws.com',
                    ])
                ),
                Statement(
                    Effect=Allow,
                    Action=[AssumeRole],
                    Principal=Principal('AWS', [
                        Sub('arn:aws:iam::${AWS::AccountId}:root'),
                        # Sub('arn:aws:iam::${AWS::AccountId}:${PrimaryRoleName}'),
                    ])
                ),
            ]),
            ManagedPolicyArns=[
                Ref(app_policy),
                'arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole',
            ]
        )
        return t.add_resource(role)

    def policy_document(self, statement):
        return PolicyDocument(
            Version='2012-10-17',
            Statement=statement)


class BucketsStack(CloudFormation):
    code = 'buckets'

    def get_template(self):
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
