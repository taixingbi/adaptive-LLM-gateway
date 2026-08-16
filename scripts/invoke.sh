#!/usr/bin/env bash
# SigV4 invoke of POST /v1/converse against the central LLM gateway.
#
# Usage:
#   ./scripts/invoke.sh
#   ./scripts/invoke.sh app-002 nova-lite "Say hello in one word."
#
# Seed apps (dev):
#   app-002 → nova-lite
#
# Requires: aws, jq, curl (with --aws-sigv4), terraform outputs for envs/dev.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="$ROOT/terraform/envs/dev"
REGION="${AWS_REGION:-us-east-1}"

APP="${1:-app-002}"
MODEL="${2:-nova-lite}"
PROMPT="${3:-Say hello in one word.}"

# Drop assumed-role session vars so terraform/aws can use your admin/SSO profile.
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

URL="$(terraform -chdir="$TF_DIR" output -raw converse_url)"
ROLE="$(terraform -chdir="$TF_DIR" output -json sample_role_arns | jq -r --arg a "$APP" '.[$a]')"

if [[ -z "$URL" || "$URL" == "null" ]]; then
  echo "converse_url is empty. Run terraform apply in $TF_DIR first." >&2
  exit 1
fi
if [[ -z "$ROLE" || "$ROLE" == "null" ]]; then
  echo "No role for app '$APP'. Known apps:" >&2
  terraform -chdir="$TF_DIR" output -json sample_role_arns | jq -r 'keys[]' >&2
  exit 1
fi

echo "app=$APP model=$MODEL"
echo "url=$URL"
echo "role=$ROLE"

creds="$(aws sts assume-role \
  --role-arn "$ROLE" \
  --role-session-name "invoke-${APP}" \
  --query Credentials \
  --output json)"

export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export AWS_SESSION_TOKEN
AWS_ACCESS_KEY_ID="$(jq -r .AccessKeyId <<<"$creds")"
AWS_SECRET_ACCESS_KEY="$(jq -r .SecretAccessKey <<<"$creds")"
AWS_SESSION_TOKEN="$(jq -r .SessionToken <<<"$creds")"

BODY="$(jq -n \
  --arg model "$MODEL" \
  --arg prompt "$PROMPT" \
  '{
    model: $model,
    messages: [{role: "user", content: [{text: $prompt}]}],
    inferenceConfig: {maxTokens: 64}
  }')"

curl -sS -X POST "$URL" \
  --aws-sigv4 "aws:amz:${REGION}:execute-api" \
  --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" \
  -H "x-amz-security-token: ${AWS_SESSION_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$BODY"
echo
