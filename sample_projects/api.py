from distmono import (
    AwsProject,
    BotoHelper,
    BuildNotFoundError,
    Deployable,
    Stack,
)
from distmono.util import sh
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
import hashlib
import shutil


class ApiProject(AwsProject):
    def get_deployables(self):
        return {
            'api-stack': ApiStack,
            'invoke-function': InvokeFunction,
            'function-stack': FunctionStack,
            # 'function-stack': MockOutput,
            'function-code': FunctionCode,
            'layer-code': LayerCode,
            'buckets-stack': BucketsStack,
            'access-stack': AccessStack,
        }

    def get_dependencies(self):
        return {
            'api-stack': 'function-stack',
            'function-stack': ['function-code', 'layer-code', 'access-stack'],
            'function-code': 'buckets-stack',
            'layer-code': 'buckets-stack',
            'buckets-stack': 'access-stack',
            'invoke-function': 'function-stack',
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


class InvokeFunction(Deployable):
    def build(self):
        resp = self.lambd.invoke(FunctionName=self.function_name)
        sh.pprint(resp)

        for chunk in resp['Payload'].iter_lines():
            sh.print(chunk)

    @cached_property
    def lambd(self):
        return self.boto.client('lambda')

    @cached_property
    def boto(self):
        # TODO: seems like AwsProject should merge into Project, makes more
        # sense to have BotoHelper(context)
        return BotoHelper(region=self.context.env['region'])

    @cached_property
    def function_name(self):
        return self.context.input['function-stack']['FunctionName']


class MockOutput(Deployable):
    def get_build_output(self):
        return {'RequestHandlerArn': 'arn:aws:lambda:ap-southeast-1:982086653134:function:distmono-sample-api-func-main'}


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
            'Function',
            FunctionName=Sub('${AWS::StackName}-function'),
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
        t.add_output(Output('FunctionName', Value=Ref(func)))
        return func

    @property
    def app_role_arn(self):
        return self.context.input['access-stack']['AppRoleArn']


class CodeMixin:
    @cached_property
    def code_base_dir(self):
        return Path(__file__).parent / 'api-code'

    def file_sha256(self, file):
        file = Path(file)
        h = hashlib.sha256()
        h.update(file.read_bytes())
        return h.hexdigest()


# TODO: this is reusable, move into distmono and unit test
class FunctionCode(Deployable, CodeMixin):
    handler = 'handler.handle'

    def build(self):
        zip_file = Path('code.zip')
        shutil.make_archive(zip_file.stem, 'zip', self.function_dir)
        zip_hash = self.file_sha256(zip_file)
        self.upload_zip_file(zip_file, zip_hash)
        zip_file.replace(self.out_zip_file)
        self.out_zip_hash_file.write_text(zip_hash)

    def upload_zip_file(self, zip_file, zip_hash):
        key = self.get_s3_zip_key(zip_hash)
        sh.print(f'Uploading {zip_file.name} to s3://{self.bucket_name}/{key}')
        self.s3.upload_file(str(zip_file), self.bucket_name, key)

    # TODO: implement is_build_outdated()

    def get_build_output(self):
        try:
            zip_hash = self.out_zip_hash_file.read_text().strip()
        except FileNotFoundError as e:
            # BuildNotFoundError seems redundant, Builder and Destroyer should
            # just catch and handle errors nicely
            raise BuildNotFoundError(str(e))

        output = {
            'Bucket': self.bucket_name,
            'Key': self.get_s3_zip_key(zip_hash),
            'Handler': self.handler,
        }
        return output

    @cached_property
    def function_dir(self):
        return self.code_base_dir / 'function'

    @cached_property
    def s3(self):
        return self.boto.client('s3')

    @cached_property
    def boto(self):
        return BotoHelper(region=self.context.env['region'])

    @property
    def bucket_name(self):
        return self.context.input['buckets-stack']['CodeBucketName']

    def get_s3_zip_key(self, zip_hash):
        return f'{zip_hash[32:]}.zip'

    @cached_property
    def out_zip_file(self):
        return self.context.build_output_dir / 'code.zip'

    @cached_property
    def out_zip_hash_file(self):
        zip_file = self.out_zip_file
        return zip_file.parent / (zip_file.name + '.sha256')


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
