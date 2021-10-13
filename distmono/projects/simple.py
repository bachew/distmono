from distmono.core import Deployable, Project
from distmono.stacker import Stack, StackerDpl
from functools import cached_property
from marshmallow import Schema, fields
from troposphere import (
    GetAtt,
    Output,
    Ref,
    s3,
    Template,
)


class EnvSchema(Schema):
    namespace = fields.Str(required=True)
    region = fields.Str(required=True)


class SimpleProject(Project):
    def load_env(self, env):
        schema = EnvSchema()
        return schema.load(env)

    def get_deployables(self):
        return {
            'lambda': LambdaDpl,
            'lambda-code': LambdaCodeDpl,
            'buckets': BucketsDpl,
        }

    def get_dependencies(self):
        return {
            'lambda': 'lambda-code',
            'lambda-code': 'buckets',
        }

    def get_default_build_target(self):
        return 'lambda'


class BucketsDpl(StackerDpl):
    def get_stacks(self):
        return [Stack('buckets', self.template)]

    @cached_property
    def template(self):
        t = Template()
        misc_bucket = self.misc_bucket
        t.add_resource(misc_bucket)
        title = misc_bucket.title
        t.add_output(Output(f'{title}Name', Value=Ref(misc_bucket)))
        t.add_output(Output(f'{title}Arn', Value=f'arn:aws:s3:::{misc_bucket.BucketName}'))
        t.add_output(Output(f'{title}DomainName', Value=GetAtt(title, 'DomainName')))
        return t

    @cached_property
    def misc_bucket(self):
        ctx = self.context
        return s3.Bucket('Misc', BucketName='{namespace}-misc'.format(**ctx.env))


# TODO
class LambdaCodeDpl(Deployable):
    def build(self):
        print('Building lambda code', self.context.input)

    def destroy(self):
        print('Destroying lambda code')


class LambdaDpl(Deployable):
    def build(self):
        # TESTING
        print('Building lambda stack', self.context.input)

    def destroy(self):
        # TESTING
        print('Destroying lambda stack')

    def get_stacks(self):
        return [
            Stack(name='lambda', template=self.template),
        ]

    @cached_property
    def template(self):
        t = Template()
        # TODO
        return t
