import json
import library


def handle(event, context):
    return {
        'statusCode': 200,
        'body': json.dumps({
            'library': library.__file__
        }),
        # 'headers': {}
    }
