from __future__ import print_function

import json
import logging
import pprint
import re

from datetime import datetime
from decimal import Decimal
from urlparse import parse_qs

import boto3
from boto3.dynamodb.conditions import Key

import requests


log = logging.getLogger()
log.setLevel(logging.INFO)

cards = boto3.resource('dynamodb').Table('coffee-cards')
inflight = boto3.resource('dynamodb').Table('coffee-cards-inflight')
transactions = boto3.resource('dynamodb').Table('coffee-cards-transactions')


def handle_kik_message(event, context):
    log.info("Received event: " + pprint.pformat(event))
    kik_api_key = event.get("kikApiKey")

    json_message = json.loads(event.get("body-json"))
    for message in json_message.get("messages"):
        chat_id = message.get("chatId")
        from_user = message.get("from")
        text = message.get("body").lower()

        body, responses = "", ""
        log.info("Recieved message: %s" % text)
        try:
            if text.startswith("return"):
                (body, responses) = pre_return_message(from_user, text)
            elif text.startswith("checkout"):
                (body, responses) = checkout_message(from_user, text)
            elif text.startswith("get"):
                body = get_card_statuses()
                responses = default_responses()
            elif text[0].isdigit() or text.startswith("$"):
                (body, responses) = return_message(from_user, text)
            else:
                raise Exception
        except Exception as e:
            log.info(e)
            body = "Sorry, I can't understand what you're trying to do."
            responses = default_responses()

        return send_kik_message(from_user, chat_id, kik_api_key, body, responses)


def handle_slack_coffee(event, context):
    expected_token = event.get('expectedToken')
    log.info(pprint.pformat(event))

    req_body = event['body']
    params = parse_qs(req_body)
    log.info(pprint.pformat(params))
    token = params['token'][0]
    if token != expected_token:
        log.error("Request token (%s) does not match expected", token)
        raise Exception("Invalid request token")

    response = {
        "text": get_card_statuses()
    }

    return response


def send_kik_message(to_user, chat_id, kik_api_key, body, responses=None):
    message = {
        'body': body,
        'to': to_user,
        'type': 'text',
        'chatId': chat_id
    }
    if responses:
        message['keyboards'] = [{
            "type": "suggested",
            "responses": responses
        }]
    res = requests.post(
        'https://api-kik-com-l7colnkdp3qc.runscope.net/v1/message',
        auth=('waterloo.coffee.bot', kik_api_key),
        headers={
            'Content-Type': 'application/json'
        },
        data=json.dumps({
            'messages': [message],
        })
    )

    log.info("Kik send message result: %d" % res.status_code)
    log.info(pprint.pformat(res.json()))
    return res.status_code


def get_card_count(provider):
    return cards.query(
        Select='COUNT',
        KeyConditionExpression=Key('provider').eq(provider)
    )['Count']


def pre_return_message(from_user, message):
    m = re.match("return ([a-z]*) card (\d)", message, re.IGNORECASE)
    if not m:
        log.info("No match found for provider & card number in message: %s" % message)
        raise Exception
    inflight.update_item(
        Key={
            'username': from_user,
            'service': 'kik'
        },
        UpdateExpression='SET op = :val1, provider = :provider, card = :card',
        ExpressionAttributeValues={
            ':val1': 'return',
            ':provider': m.group(1),
            ':card': Decimal(m.group(2))
        }
    )
    return ("Sweet! How much is left on the card? (Just the number please!)", None)


def return_message(from_user, message):
    m = re.match("\$?(\d*\.?\d?\d?)", message)
    req = inflight.get_item(
        Key={
            'service': 'kik',
            'username': from_user
        }
    )['Item']
    log.info("Got inflight item: {}".format(req))
    if req.get("op") != "return":
        return ("You have to tell me what card you're returning first...", default_responses())
    return_card(req.get("provider"), req.get("card"), m.group(1), from_user)
    return ("Thanks for returning {} Card {}, {}! What do you want to do next?".format(
            req.get("provider").capitalize(),
            req.get("card"),
            from_user
            ),
            default_responses())


def return_card(provider, number, value, from_user):
    cards.update_item(
        Key={
            'provider': provider,
            'card_number': Decimal(number)
        },
        UpdateExpression='SET person = :val1, card_value = :value',
        ExpressionAttributeValues={
            ':val1': None,
            ':value': Decimal(value)
        }
    )
    date = datetime.utcnow()
    check_transaction_record_exists(date)
    transactions.update_item(
        Key={
            'date': datetime.strftime(date, "%Y-%m-%d")
        },
        UpdateExpression='SET transactions = list_append(transactions, :val1)',
        ExpressionAttributeValues={
            ':val1': ["{},{},{},{},{}".format(
                provider, number, value, from_user, date.strftime('%Y-%m-%d %H:%M:%S'))
            ]
        },
        ReturnValues='NONE'
    )


def check_transaction_record_exists(date):
    date = datetime.strftime(date, "%Y-%m-%d")
    t = transactions.get_item(
        Key={
            'date': date
        })
    if not t.get("Item"):
        transactions.put_item(
            Item={
                'date': date,
                'transactions': []
            }
        )


def checkout_message(from_user, message):
    m = re.match("checkout ([a-z]*) card (\d)", message, re.IGNORECASE)
    if not m:
        log.info("No match found for provider & card number in message: %s" % message)
        raise Exception
    provider = m.group(1)
    card_number = m.group(2)
    checkout_card(provider, card_number, from_user)
    return ("Thanks! {} Card {} is now checked out to you!".format(
            provider.capitalize(), card_number),
            [{"type": "text", "body": "Return {} Card {}".format(
                provider.capitalize(), card_number)}]
            )


def checkout_card(provider, number, person):
    log.info("Assigning {} card {} to {}".format(provider, number, person))
    cards.update_item(
        Key={
            'provider': provider,
            'card_number': Decimal(number)
        },
        UpdateExpression='SET person = :val1',
        ExpressionAttributeValues={
            ':val1': person
        }
    )


def get_card_statuses():
    log.info("Fetching card statuses")
    card_list = cards.scan()['Items']
    response = []
    for card in card_list:
        if card.get("person"):
            r = "{} card {} is checked out by @{}.".format(
                card.get("provider").capitalize(), card.get("card_number"), card.get("person"))
        else:
            r = "{} card {} is available, current value is ${}.".format(
                card.get("provider").capitalize(),
                card.get("card_number"),
                card.get("card_value", Decimal("0.00"))
            )
        response.append(r)
    return " ".join(response)


def default_responses():
    log.info("Fetching default responses")
    responses = [{"type": "text", "body": "Get Card Statuses"}]
    card_list = cards.scan()['Items']
    for card in card_list:
        if card.get("person"):
            responses.append({"type": "text", "body": "Return {} Card {}".format(
                card.get("provider").capitalize(), card.get("card_number"))})
        else:
            responses.append({"type": "text", "body": "Checkout {} Card {}".format(
                card.get("provider").capitalize(), card.get("card_number"))})
    return responses
