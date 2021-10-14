from distmono import (
    AwsProject,
    Deployable,
    Stack,
)
from troposphere import (
    GetAtt,
    iam,
    awslambda as lambd,
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
import shutil


class ApiProject(AwsProject):
    def get_deployables(self):
        return {
            'api-stack': ApiStack,
            'function-stack': FunctionStack,
            'function-code': FunctionCode,
            'layer-code': LayerCode,
            'buckets-stack': BucketsStack,
            'access-stack': AccessStack,
            'invoke-function': InvokeFunction,

            'test': Deployable,
        }

    def get_dependencies(self):
        return {
            'api-stack': 'function-stack',
            'function-stack': ['function-code', 'layer-code', 'access-stack'],
            # 'function-code': 'buckets-stack',
            # 'layer-code': 'buckets-stack',
            'buckets-stack': 'access-stack',
            'invoke-function': 'function-stack',

            'test': ['function-code', 'layer-code'],
        }

    def get_default_build_target(self):
        return 'api-stack'


class ApiStack(Stack):
    code = 'api'

    def get_template(self):
        t = Template()
        # TODO
        t.add_resource(s3.Bucket(
            'DummyBucket',
            BucketName=Sub('${AWS::StackName}-dummy-bucket')))
        return t


class FunctionStack(Stack):
    code = 'func'

    def get_template(self):
        t = Template()
        layer = self.add_layer(t)
        self.add_function(t, layer)
        return t

    def add_layer(self, t):
        pass  # TODO: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-lambda-layerversion.html

    def add_function(self, t, layer):
        code_input = self.context.input['function-code']
        func = lambd.Function(
            'RequestHandler',
            FunctionName=Sub('${AWS::StackName}-main'),
            Code=lambd.Code(
                S3Bucket=code_input['Bucket'],
                S3Key=code_input['Key'],
            ),
            Runtime='python3.7',
            Handler=code_input['Handler'],
            Role=self.app_role_arn,
            # MemorySize=128,
            # Timeout=30,
        )
        t.add_resource(func)
        t.add_output(Output('RequestHandlerArn', Value=GetAtt(func, 'Arn')))
        return func

    @property
    def app_role_arn(self):
        return self.context.input['access-stack']['AppRoleArn']


class InvokeFunction(Deployable):
    def build(self):
        print(f'TODO: invoke function, input={self.context.input}')


class CodeMixin:
    @cached_property
    def code_base_dir(self):
        return Path(__file__).parent / 'api-code'


class FunctionCode(Deployable, CodeMixin):
    def build(self):
        shutil.make_archive('code', 'zip', self.function_dir)
        # TODO: hash and rename
        # TODO: upload to bucket
        # TODO: write to output dir

    @property
    def bucket_name(self):
        # return 'testing'
        return self.context.input['buckets-stack']['CodeBucketName']

    def get_build_output(self):
        # TODO: read from output dir
        output = {
            'Bucket': self.bucket_name,
            'Key': '',  # TODO
            'Handler': 'handler.handle',
        }
        return output

    @cached_property
    def function_dir(self):
        return self.code_base_dir / 'function'


class LayerCode(Deployable, CodeMixin):
    def build(self):
        # TODO: clone layer dir and install requirements in it before zipping
        shutil.make_archive('layer', 'zip', self.layer_dir, 'python')
        # TODO: follow FunctionCode

    @cached_property
    def layer_dir(self):
        return self.code_base_dir / 'layer'


class BucketsStack(Stack):
    code = 'buckets'

    def get_template(self):
        t = Template()
        self.add_code_bucket(t)
        return t

    def add_code_bucket(self, t):
        bucket = s3.Bucket(
            'CodeBucket2',
            BucketName=Sub('${AWS::StackName}-code'),
            AccessControl=s3.BucketOwnerFullControl,
            LifecycleConfiguration=s3.LifecycleConfiguration(
                Rules=[
                    s3.LifecycleRule(
                        AbortIncompleteMultipartUpload=s3.AbortIncompleteMultipartUpload(
                            DaysAfterInitiation=1,
                        ),
                        Status='Enabled',
                    )
                ],
            ),
        )
        t.add_resource(bucket)
        t.add_output(Output(f'CodeBucketName', Value=Ref(bucket)))
        return bucket


class AccessStack(Stack):
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
        t.add_resource(policy)
        return policy

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
        t.add_resource(role)
        t.add_output(Output('AppRoleArn', Value=GetAtt(role, 'Arn')))
        return role

    def policy_document(self, statement):
        return PolicyDocument(
            Version='2012-10-17',
            Statement=statement)
