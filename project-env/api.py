from sample_projects.api import ApiProject


def get_project():
    return ApiProject(env=get_env())


def get_env():
    return {
        'namespace': 'distmono-sample-api',  # prefix for all stack names
        'region': 'ap-southeast-1',
    }
