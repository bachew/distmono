import attr


@attr.s(kw_only=True)
class Stacker:
    region = attr.ib()
    recreate_failed = attr.ib(default=True)

    def build(self, config, env):
        # stacker -r region --recreate-failed env.yaml config.yaml
        pass


@attr.s(kw_only=True)
class Config:
    namespace = attr.ib(default='${namespace}')
    stacker_bucket = attr.ib(default='')
    # TODO: sys_path
    stacks = attr.ib(default=attr.Factory(list))
    tags = attr.ib(default=attr.Factory(dict))


@attr.s(kw_only=True)
class Stack:
    name = attr.ib()
    blueprint = attr.ib()
    variables = attr.ib(default=attr.Factory(dict))
    tags = attr.ib(default=attr.Factory(dict))
