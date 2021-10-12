from distmono.core import Deployable, Project
from distmono.stacker import Stack, StackerDpl
from functools import cached_property
from troposphere import (
    AWSHelperFn,
    GetAtt,
    Output,
    Ref,
    Sub,
    s3,
    Template,
)


class SimpleProject(Project):
    def get_deployables(self):
        return {
            'buckets': BucketsDpl,
            'lambda-code': LambdaCodeDpl,
            # 'lambda': LambdaDpl,
        }

    # TODO
    def get_dependencies(self):
        return {
            'lambda': 'lambda-code',
            'lambda-code': 'buckets',
        }


class BucketsDpl(StackerDpl):
    def get_stacks(self):
        return [
            Stack(name='buckets', template=self.template),
        ]

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
        return s3.Bucket('Misc', BucketName='{namespace}-misc'.format(**ctx.config))


class LambdaCodeDpl(Deployable):
    pass  # TODO


class LambdaDpl(StackerDpl):
    def get_stacks(self):
        return [
            Stack(name='lambda', template=self.template),
        ]

    @cached_property
    def template(self):
        t = Template()
        # TODO
        return t
