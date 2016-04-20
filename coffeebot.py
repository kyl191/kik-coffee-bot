from __future__ import print_function

import boto3
from boto3.dynamodb.conditions import Attr
import pprint
import logging
import requests
import json

log = logging.getLogger()
log.setLevel(logging.INFO)

def lambda_handler(event, context):
    '''Provide an event that contains the following keys:

      - operation: one of the operations in the operations dict below
      - tableName: required for operations that interact with DynamoDB
      - payload: a parameter to pass to the operation being performed
    '''
    log.info("Received event: " + pprint.pformat(event))

    dynamo = boto3.resource('dynamodb').Table('coffee-cards')

    test = dynamo.scan(
        FilterExpression=Attr('person').ne(None)
    )

    apiKey = event.get("kikApiKey")

    json_message = json.loads(event.get("body-json"))

    for message in json_message.get("messages"):

        chatId = message.get("chatId")
        fromUser = message.get("from")
        text = message.get("body")

        res = requests.post(
            'https://api-kik-com-l7colnkdp3qc.runscope.net/v1/message',
            auth=('waterloo.coffee.bot', apiKey),
            headers={
                'Content-Type': 'application/json'
            },
            data=json.dumps({
                'messages': [
                    {
                        'body': "You said %s, Used cards: %d" % (text, test['Count']),
                        'to': fromUser,
                        'type': 'text',
                        'chatId': chatId
                    }
                ]
            })
        )

        log.info("Kik send message result: %d" % res.status_code)
        log.info(pprint.pformat(res.json()))

    return None

