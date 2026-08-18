#!/usr/bin/env bash
# SigV4 invoke of POST /v1/infer (experiment path, Nova Micro + admission).
#
# Usage:
#   ./scripts/infer.sh
#   ./scripts/infer.sh tenant-007 medium

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="$ROOT/terraform/envs/dev"
REGION="${AWS_REGION:-us-east-1}"

TENANT="${1:-tenant-001}"
PROMPT_CLASS="${2:-short}"

unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

URL="$(terraform -chdir="$TF_DIR" output -raw infer_url)"
ROLE="$(terraform -chdir="$TF_DIR" output -json sample_role_arns | jq -r '.["app-002"]')"

echo "tenant=$TENANT prompt_class=$PROMPT_CLASS"
echo "url=$URL"

creds="$(aws sts assume-role \
  --role-arn "$ROLE" \
  --role-session-name "infer-${TENANT}" \
  --query Credentials \
  --output json)"

export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
AWS_ACCESS_KEY_ID="$(jq -r .AccessKeyId <<<"$creds")"
AWS_SECRET_ACCESS_KEY="$(jq -r .SecretAccessKey <<<"$creds")"
AWS_SESSION_TOKEN="$(jq -r .SessionToken <<<"$creds")"

BODY="$(jq -n \
  --arg tenant "$TENANT" \
  --arg class "$PROMPT_CLASS" \
  '{tenant_id: $tenant, prompt_class: $class}')"

curl -sS -X POST "$URL" \
  --aws-sigv4 "aws:amz:${REGION}:execute-api" \
  --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" \
  -H "x-amz-security-token: ${AWS_SESSION_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$BODY"
echo
