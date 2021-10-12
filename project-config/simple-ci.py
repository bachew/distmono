from distmono.projects.simple import SimpleProject
from pathlib import Path


def get_project():
    return SimpleProject(
        project_dir=Path(__file__).parents[1],
        env=get_env())


def get_env():
    return {
        'namespace': 'distmono-simple',
        'region': 'ap-southeast-1',
    }
