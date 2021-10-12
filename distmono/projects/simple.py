from distmono.core import Project
from distmono.stacker import Stack, StackerDpl
from stacker_blueprints.s3 import Buckets


class SimpleProject(Project):
    def get_deployables(self):
        return {
            'buckets': BucketsDpl,
        }


class BucketsDpl(StackerDpl):
    def get_stacks(self):
        return [
            Stack(name='buckets', blueprint=Buckets, variables={
                'Buckets': {
                    'MiscBucket': {
                        'BucketName': '${namespace}-misc',
                    }
                }
            }),
        ]

    def destroy(self, ctx):
        pass  # TODO
