from distmono.projects.simple import SimpleProject
from pathlib import Path


def get_project():
    return SimpleProject(
        project_dir=Path(__file__).parents[1],
        config=get_config())


def get_config():
    return {
        'namespace': 'distmono-simple',
        'region': 'ap-southeast-1'
    }
