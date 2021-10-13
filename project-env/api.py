from distmono.projects.api import ApiProject
from pathlib import Path


def get_project():
    return ApiProject(
        project_dir=Path(__file__).parents[1],
        env=get_env())


def get_env():
    return {
        'namespace': 'distmono-api',
        'region': 'ap-southeast-1',
    }
