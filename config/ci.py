from distmono.core import Project
from pathlib import Path


def get_project():
    project_dir = Path(__file__).parents[1]
    project = Project(project_dir=project_dir)
    return project
