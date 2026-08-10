#!/usr/bin/env bash
set -euo pipefail

: "${AUTH0_DOMAIN:?Set AUTH0_DOMAIN}"
: "${CLIENT_ID:?Set CLIENT_ID}"
: "${CLIENT_SECRET:?Set CLIENT_SECRET}"
: "${CONDUIT_AUDIENCE:=https://conduit-mcp.onrender.com/mcp}"

TOKEN="$(curl -fsS --request POST "https://${AUTH0_DOMAIN}/oauth/token" \
  --header 'content-type: application/json' \
  --data "{\"client_id\":\"${CLIENT_ID}\",\"client_secret\":\"${CLIENT_SECRET}\",\"audience\":\"${CONDUIT_AUDIENCE}\",\"grant_type\":\"client_credentials\"}" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"

printf '%s\n' "$TOKEN"
