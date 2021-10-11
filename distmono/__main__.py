from distmono.core import BuildTool
from pathlib import Path
import click
import subprocess


base_dir = Path(__file__).parents[1]
build_tool = BuildTool(base_dir=base_dir)


@click.group()
def cli():
    pass


@cli.command('run', context_settings=dict(
    help_option_names=[],
    ignore_unknown_options=True,
))
@click.pass_context
@click.argument('command', nargs=-1, type=click.UNPROCESSED,
                metavar='PROGRAM [ARGS]...')
def cli_run(ctx, command):
    '''
    Run a command in virtual environment.
    '''

    def help_exit():
        print(ctx.get_help())
        raise SystemExit(1)

    if not command:
        help_exit()

    try:
        res = subprocess.run(command, check=False)
    except FileNotFoundError:
        click.echo('Error: command not found: {}'.format(command[0]), err=True)
        help_exit()
    else:
        raise SystemExit(res.returncode)


@cli.command('build')
def cli_build():
    from distmono.stacker import Stacker, Stack, Config
    from stacker_blueprints.s3 import Buckets

    stacker = Stacker(build_tool=build_tool, region='ap-southeast-1')
    stacks = [
        Stack(name='buckets', blueprint=Buckets, variables={
            'Buckets': {
                'MiscBucket': {
                    'BucketName': '${namespace}-misc',
                }
            }
        }),
    ]
    config = Config(namespace='distmono', stacks=stacks)
    stacker.build(config, {
        'namespace': 'distmono'
    })


cli(prog_name='dmn')
