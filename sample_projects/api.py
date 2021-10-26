from distmono import (
    Project,
    Deployable,
    Stack,
)
from distmono.util import BotoHelper, sh
from cached_property import cached_property
from troposphere import (
    apigateway as apigw,
    AWSHelperFn,
    awslambda as lambd,
    GetAtt,
    iam,
    Output,
    Ref,
    s3,
    Sub,
    Template,
)
from pathlib import Path
from awacs.aws import Action, Allow, PolicyDocument, Principal, Statement
from awacs.sts import AssumeRole
from os import path as osp
from textwrap import indent
import hashlib
import json
import shutil
import urllib.request


class ApiProject(Project):
    def __init__(self, **kwargs):
        kwargs['project_dir'] = Path(__file__).parents[1]
        super().__init__(**kwargs)

    def get_deployables(self):
        return {
            'api-stack': ApiStack,
            'function-stack': FunctionStack,
            'function-code': FunctionCode,
            'layer-code': LayerCode,
            'buckets-stack': BucketsStack,
            'access-stack': AccessStack,

            'call-api': CallApi,
            'invoke-function': InvokeFunction,
            # 'test': SimpleTest,
            'test': Deployable,
        }

    def get_dependencies(self):
        return {
            'api-stack': ['function-stack', 'access-stack'],
            'function-stack': ['function-code', 'layer-code', 'access-stack'],
            'function-code': 'buckets-stack',
            'layer-code': 'buckets-stack',
            # 'buckets-stack': 'access-stack',

            'call-api': 'api-stack',
            'invoke-function': 'function-stack',
            # 'test': 'buckets-stack',
            'test': ['invoke-function', 'call-api'],
        }

    def get_default_build_target(self):
        return 'api-stack'


class ApiStack(Stack):
    stack_code = 'api'

    def get_template(self):
        t = Template()
        api = self.add_api(t)
        deployment = self.add_deployment(t, api)
        stage = self.add_stage(t, api, deployment)
        t.add_output(Output(
            'ApiUrl',
            Value=Sub(f'https://${{Api}}.execute-api.${{AWS::Region}}.amazonaws.com/{stage.StageName}')
        ))
        return t

    def add_api(self, t):
        api = apigw.RestApi(
            'Api',
            Name=Sub('${AWS::StackName}-rest-api'),
            EndpointConfiguration=apigw.EndpointConfiguration(
                Types=['REGIONAL'],
            ),
            Body=self.get_api_spec(),
        )
        # TODO: add ApiKey, UsagePlan and UsagePlanKey
        t.add_resource(api)
        t.add_output(Output('ApiId', Value=Ref(api)))
        return api

    def get_api_spec(self):
        api_integration = self.get_api_integration()
        api_spec = {
            'swagger': '2.0',
            'info': {
                'title': Sub('${AWS::StackName}-rest-api'),
                'description': 'API',
                'version': '1.0.0'
            },
            'schemes': ['https'],
            'produces': ['application/json'],
            'securityDefinitions': {
                'apiKeyAuth': {
                    'in': 'header',
                    'name': 'x-api-key',
                    'type': 'apiKey'
                }
            },
            'paths': {
                '/status': {
                    'x-amazon-apigateway-any-method': {
                        'responses': {
                            '200': {'description': 'OK'}
                        },
                        'x-amazon-apigateway-integration': api_integration
                    }
                },
                '/{proxy+}': {
                    'x-amazon-apigateway-any-method': {
                        'parameters': [
                            {
                                'in': 'path',
                                'name': 'proxy',
                                'required': True,
                                'type': 'string'
                            }
                        ],
                        'responses': {
                            '200': {'description': 'OK'}
                        },
                        'security': [
                            {'apiKeyAuth': []}
                        ],
                        'x-amazon-apigateway-integration': api_integration
                    }
                }
            }
        }
        return api_spec

    def get_api_integration(self):
        region = self.context.env['region']
        app_role_arn = self.context.input['access-stack']['AppRoleArn']
        function_arn = self.context.input['function-stack']['FunctionArn']
        return {
            'contentHandling': 'CONVERT_TO_TEXT',
            'credentials': app_role_arn,
            'httpMethod': 'POST',
            'passthroughBehavior': 'when_no_templates',
            'type': 'aws_proxy',
            'uri': f'arn:aws:apigateway:{region}:lambda:path/2015-03-31/functions/{function_arn}/invocations'
        }

    def add_deployment(self, t, api):
        body_bytes = self.dump_api_body(api.Body).encode('utf')
        body_hash = self.sha256(body_bytes)[16:]
        deployment = apigw.Deployment(
            # XXX: suffix body hash to force deployment whenever body changes
            f'Deployment{body_hash}',
            RestApiId=Ref(api),
        )
        t.add_resource(deployment)
        return deployment

    def dump_api_body(self, body):
        class AwsHelperFnEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, AWSHelperFn):
                    return obj.data

                return super().default(obj)

        return json.dumps(body, cls=AwsHelperFnEncoder)

    def sha256(self, data):
        h = hashlib.sha256()
        h.update(data)
        return h.hexdigest()

    def add_stage(self, t, api, deployment):
        stage = apigw.Stage(
            'Stage',
            StageName='dev',  # doesn't matter
            RestApiId=Ref(api),
            DeploymentId=Ref(deployment),
        )
        t.add_resource(stage)
        return stage


class FunctionStack(Stack):
    stack_code = 'func'

    def get_template(self):
        t = Template()
        layer = self.add_layer(t)
        self.add_function(t, layer)
        return t

    def add_layer(self, t):
        input_code = self.context.input['layer-code']
        layer = lambd.LayerVersion(
            'Layer',
            LayerName=Sub('${AWS::StackName}-layer'),
            CompatibleRuntimes=['python3.7'],
            Content=lambd.Content(
                S3Bucket=input_code['Bucket'],
                S3Key=input_code['Key'],
            ),
        )
        t.add_resource(layer)
        return layer

    def add_function(self, t, layer):
        input_code = self.context.input['function-code']
        func = lambd.Function(
            'Function',
            FunctionName=Sub('${AWS::StackName}-function'),
            Code=lambd.Code(
                S3Bucket=input_code['Bucket'],
                S3Key=input_code['Key'],
            ),
            Layers=[Ref(layer)],
            Runtime='python3.7',
            Handler='handler.handle',
            Role=self.app_role_arn,
            MemorySize=128,
            Timeout=30,
        )
        t.add_resource(func)
        t.add_output(Output('FunctionName', Value=Ref(func)))
        t.add_output(Output('FunctionArn', Value=GetAtt(func, 'Arn')))
        return func

    @property
    def app_role_arn(self):
        return self.context.input['access-stack']['AppRoleArn']


# TODO: this is reusable, move into distmono and unit test
class Code(Deployable):
    @cached_property
    def code_base_dir(self):
        return Path(__file__).parent / 'api-code'

    def build(self):
        zip_file = Path('code.zip')
        self.zip(zip_file.stem)
        zip_hash = self.file_sha256(zip_file)
        sh.print("TODO: don't upload if already uploaded")
        self.upload_zip_file(zip_file, zip_hash)
        zip_file.replace(self.out_zip_file)
        self.out_zip_hash_file.write_text(zip_hash)

    def zip(self, stem):
        raise NotImplementedError

    def file_sha256(self, file):
        file = Path(file)
        h = hashlib.sha256()
        h.update(file.read_bytes())
        return h.hexdigest()

    def upload_zip_file(self, zip_file, zip_hash):
        key = self.get_s3_zip_key(zip_hash)
        sh.print(f'Uploading {zip_file.name} to s3://{self.bucket_name}/{key}')
        self.s3.upload_file(str(zip_file), self.bucket_name, key)

    # TODO: implement is_build_outdated()

    def get_build_output(self):
        zip_hash = self.out_zip_hash_file.read_text().strip()
        return {
            'Bucket': self.bucket_name,
            'Key': self.get_s3_zip_key(zip_hash),
        }

    @cached_property
    def s3(self):
        return self.boto.client('s3')

    @cached_property
    def boto(self):
        return BotoHelper.from_context(self.context)

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

    def destroy(self):
        sh.print(f'Clearing S3 bucket {self.bucket_name!r}')
        s3 = self.boto.resource('s3')
        bucket = s3.Bucket(self.bucket_name)
        # TODO: should only delete function or layer code
        bucket.objects.all().delete()


class FunctionCode(Code):
    def zip(self, stem):
        function_dir = self.code_base_dir / 'function'
        shutil.make_archive(stem, 'zip', function_dir)


class LayerCode(Code):
    def zip(self, stem):
        # TODO: move to build dir, download libraries from requirements etc
        layer_dir = self.code_base_dir / 'layer'
        shutil.make_archive(stem, 'zip', layer_dir, 'python')


class BucketsStack(Stack):
    stack_code = 'buckets'

    def get_template(self):
        t = Template()
        self.add_code_bucket(t)
        return t

    def add_code_bucket(self, t):
        bucket = s3.Bucket(
            'CodeBucket',
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
    stack_code = 'access'

    def get_template(self):
        t = Template()
        app_policy = self.add_app_policy(t)
        self.add_app_role(t, app_policy)
        return t

    def add_app_policy(self, t):
        policy = iam.ManagedPolicy(
            'AppPolicy',
            ManagedPolicyName=Sub('${AWS::StackName}-app-policy'),
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
            RoleName=Sub('${AWS::StackName}-app-role'),
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


class CallApi(Deployable):
    def build(self):
        base_url = self.context.input['api-stack']['ApiUrl']
        status_url = osp.join(base_url, 'status')
        sh.print(f'GET {status_url}')

        with urllib.request.urlopen(status_url) as r:
            sh.print(indent(r.read().decode('utf8'), '  '))


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
        return BotoHelper.from_context(self.context)

    @cached_property
    def function_name(self):
        return self.context.input['function-stack']['FunctionName']


class SimpleTest(Deployable):
    def build(self):
        bucket_name = self.context.input['buckets-stack']['CodeBucketName']
        sh.print(f'Clearing S3 bucket {bucket_name!r}')
        s3 = BotoHelper.from_context(self.context).resource('s3')
        bucket = s3.Bucket(bucket_name)
        bucket.objects.all().delete()
