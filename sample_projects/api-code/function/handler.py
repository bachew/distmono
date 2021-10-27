import json
import library  # verify that layer code works


def handle(event, context):
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': library.hello()
        }),
    }
