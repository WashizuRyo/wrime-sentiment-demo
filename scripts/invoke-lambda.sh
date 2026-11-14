#!/usr/bin/env bash
set -euo pipefail

function_name="$(aws cloudformation describe-stacks --stack-name WrimeInference \
  --query "Stacks[0].Outputs[?OutputKey=='FunctionName'].OutputValue | [0]" --output text)"
mkdir -p .local
node -e 'process.stdout.write(JSON.stringify({text: process.env.TEXT || "今日はとても楽しかった！"}))' \
  > .local/lambda-request.json
time aws lambda invoke --function-name "$function_name" \
  --payload fileb://.local/lambda-request.json --log-type Tail \
  .local/lambda-response.json > .local/lambda-metadata.json
cat .local/lambda-response.json
printf '\n'
