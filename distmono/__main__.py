from distmono.core import load_project_config
from pathlib import Path
import click
import subprocess


@click.group()
@click.option('-c', '--config', 'config_file',
              required=True,
              help='Project config file (e.g. config/ci.py)')
@click.pass_context
def cli(ctx, config_file):
    ctx.obj = load_project_config(config_file)


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
@click.pass_obj
def cli_build(project):
    # TODO
    print(project)


@cli.command('build-buckets')
def cli_build_buckets():
    from distmono.core import Project
    from distmono.stacker import Stacker, Stack, Config
    from stacker_blueprints.s3 import Buckets

    project_dir = Path(__file__).parents[1]
    project = Project(project_dir=project_dir)
    stacker = Stacker(project=project, region='ap-southeast-1')
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
