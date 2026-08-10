#!/usr/bin/env bash
set -euo pipefail

# End-to-end smoke test for a deployed Conduit instance.
# Required: curl, sed, grep, mktemp.
# Credentials are read from environment variables and never printed.

: "${AUTH0_DOMAIN:?Set AUTH0_DOMAIN}"
: "${CLIENT_ID:?Set CLIENT_ID}"
: "${CLIENT_SECRET:?Set CLIENT_SECRET}"
: "${CONDUIT_URL:=https://conduit-mcp-nfmm.onrender.com/mcp}"
: "${CONDUIT_AUDIENCE:=https://conduit-mcp.onrender.com/mcp}"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

say() { printf '\n==> %s\n' "$1"; }

say "Request Auth0 access token"
token_response="$(curl -fsS -X POST "https://${AUTH0_DOMAIN}/oauth/token" \
  -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"${CLIENT_ID}\",\"client_secret\":\"${CLIENT_SECRET}\",\"audience\":\"${CONDUIT_AUDIENCE}\",\"grant_type\":\"client_credentials\"}")"
TOKEN="$(printf '%s' "$token_response" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')"
[ -n "$TOKEN" ] || { echo "Auth0 did not return an access token" >&2; exit 1; }
printf 'Access token: obtained (not printed)\n'

request() {
  local name="$1" data="$2"
  local headers="$workdir/${name}.headers" body="$workdir/${name}.body"
  local status
  status="$(curl -sS -D "$headers" -o "$body" -w '%{http_code}' "$CONDUIT_URL" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -H 'MCP-Protocol-Version: 2025-06-18' \
    ${SESSION_HEADER:+-H "$SESSION_HEADER"} \
    -d "$data")"
  printf '%s status: %s\n' "$name" "$status"
  printf '%s' "$status" > "$workdir/${name}.status"
}

say "Initialize MCP session"
request initialize '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"conduit-smoke-test","version":"1.0.0"}}}'
[ "$(cat "$workdir/initialize.status")" = "200" ] || { cat "$workdir/initialize.body"; exit 1; }

SESSION_ID="$(sed -n 's/^mcp-session-id: *//Ip' "$workdir/initialize.headers" | tr -d '\r' | head -n1)"
[ -n "$SESSION_ID" ] || { echo "Conduit did not return mcp-session-id" >&2; exit 1; }
SESSION_HEADER="Mcp-Session-Id: ${SESSION_ID}"
printf 'MCP session: established\n'

say "Mark session initialized"
request initialized '{"jsonrpc":"2.0","method":"notifications/initialized"}'
[ "$(cat "$workdir/initialized.status")" = "202" ] || { cat "$workdir/initialized.body"; exit 1; }

say "List tools"
request tools_list '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
[ "$(cat "$workdir/tools_list.status")" = "200" ] || { cat "$workdir/tools_list.body"; exit 1; }
grep -q '"name":"github_repo_info"' "$workdir/tools_list.body" || { echo "github_repo_info was not advertised" >&2; cat "$workdir/tools_list.body"; exit 1; }
printf 'Tool discovery: github_repo_info present\n'

say "Call github_repo_info"
request tool_call '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"github_repo_info","arguments":{"owner":"devXyi","repo":"conduit-mcp"}}}'
[ "$(cat "$workdir/tool_call.status")" = "200" ] || { cat "$workdir/tool_call.body"; exit 1; }
grep -q '"isError":false' "$workdir/tool_call.body" || { cat "$workdir/tool_call.body"; exit 1; }

echo
printf 'PASS: Auth0 → Conduit → MCP session → tools/list → github_repo_info\n'
