from __future__ import print_function

import boto3
import json
import logging
import pprint
import requests

from boto3.dynamodb.conditions import Attr
from urlparse import parse_qs

log = logging.getLogger()
log.setLevel(logging.INFO)

cards = boto3.resource('dynamodb').Table('coffee-cards')

def handleKikMessage(event, context):
    log.info("Received event: " + pprint.pformat(event))

    test = get_used_cards()

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

    # Send something back so API Gateway doesn't send a null
    return ""

def handleSlackCoffee(event, context):
    expected_token = event.get('expectedToken')
    log.info(pprint.pformat(event))

    req_body = event['body']
    params = parse_qs(req_body)
    log.info(pprint.pformat(params))
    token = params['token'][0]
    if token != expected_token:
        log.error("Request token (%s) does not match exptected", token)
        raise Exception("Invalid request token")

    test = get_used_cards()

    response = {
        "text": "Used cards: %d" % test['Count']
    }

    return response

def get_used_cards():
    # We have 3-4 cards, .scan works fine.
    # For anything bigger, this would be a secondary index
    return cards.scan(
        FilterExpression=Attr('person').ne(None)
    )
