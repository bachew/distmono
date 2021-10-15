from distmono.core import load_project
from pprint import pprint
import click
import subprocess


@click.group()
@click.option('-p', '--project-env', 'file',
              required=True,
              help='Project and env file (e.g. project-env/simple-ci.py)')
@click.pass_context
def cli(ctx, file):
    ctx.obj = load_project(file)


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
@click.argument('target', required=False)
@click.pass_obj
def cli_build(project, target):
    output = project.build(target)
    pprint(output)


@cli.command('destroy')
@click.argument('target', required=False)
@click.pass_obj
def cli_destroy(project, target):
    project.destroy(target)


cli(prog_name='dmn')
