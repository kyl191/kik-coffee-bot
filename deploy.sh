#!/bin/bash
set -e

if [ ! -d "requests-2.9.1.dist-info" ]; then
    pip install requests -t .
fi
rm -f ../coffeebot.zip
zip -r ../coffeebot.zip .
aws s3 cp ../coffeebot.zip "s3://kik-coffee-bot/coffeebot.zip" --profile production
aws lambda update-function-code --function-name incomingKikMessage --s3-bucket kik-coffee-bot --s3-key "coffeebot.zip" --publish --profile production --region us-east-1
aws lambda update-function-code --function-name incomingSlackCoffee --s3-bucket kik-coffee-bot --s3-key "coffeebot.zip" --publish --profile production --region us-east-1
