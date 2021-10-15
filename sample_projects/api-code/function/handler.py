import library


def handle(event, context):
    return {
        'library': 'library.__file__'
    }
