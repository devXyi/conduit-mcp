# Connect to Conduit remotely

Conduit can be consumed as a remote MCP server without cloning the repository.

## Production endpoints

- Service: `https://conduit-mcp-nfmm.onrender.com/`
- Health: `https://conduit-mcp-nfmm.onrender.com/health`
- MCP: `https://conduit-mcp-nfmm.onrender.com/mcp`
- Protected-resource metadata: `https://conduit-mcp-nfmm.onrender.com/.well-known/oauth-protected-resource`

`/health` is public. `/mcp` requires a bearer access token.

## Capability model

Conduit uses two application-level capabilities:

```text
conduit:read
    └── workspace + GitHub tools

conduit:admin
    └── Auth0 Management API tools
```

A caller with only `conduit:read` cannot invoke `auth0_list_applications` or `auth0_get_application`. Those tools enforce `conduit:admin` immediately before touching the server-side Auth0 Management API client.

This is deliberately separate from Auth0's own Management API scopes. A Conduit caller's `conduit:admin` permission does **not** itself grant `read:client_keys`, `read:client_credentials`, or any other downstream Auth0 scope.

## Recommended integration model

Each consuming application should use **its own Auth0 client credentials**. Never give another developer Conduit's server-side Management API secret.

```text
Your application
      │ Client Credentials
      ▼
    Auth0
      │ access token for Conduit
      ▼
  Conduit MCP
      │
      ├── conduit:read  → Workspace / GitHub
      └── conduit:admin → Auth0 admin tools
```

Conduit is the OAuth resource server. Auth0 is the authorization server.

## Current resource configuration

```text
Issuer:
https://dev-jf6pbb4exdzatprm.eu.auth0.com/

Audience:
https://conduit-mcp.onrender.com/mcp

Normal consumer scope:
conduit:read

Administrative Conduit scope:
conduit:admin
```

## Request a normal consumer token

Use your own Auth0 Machine-to-Machine application:

```bash
export AUTH0_DOMAIN="dev-jf6pbb4exdzatprm.eu.auth0.com"
export CLIENT_ID="your-client-id"
export CLIENT_SECRET="your-client-secret"
export CONDUIT_AUDIENCE="https://conduit-mcp.onrender.com/mcp"

TOKEN=$(curl -sS --request POST "https://${AUTH0_DOMAIN}/oauth/token" \
  --header "content-type: application/json" \
  --data "{\"client_id\":\"${CLIENT_ID}\",\"client_secret\":\"${CLIENT_SECRET}\",\"audience\":\"${CONDUIT_AUDIENCE}\",\"grant_type\":\"client_credentials\"}" \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

[ -n "$TOKEN" ] || { echo "Auth0 did not return an access token" >&2; exit 1; }
```

Never commit or publish client secrets or access tokens.

## Remote MCP session

Use:

```text
https://conduit-mcp-nfmm.onrender.com/mcp
```

The client should:

```text
1. obtain an Auth0 access token
2. initialize MCP
3. retain Mcp-Session-Id
4. send notifications/initialized
5. call tools/list or tools/call
```

A valid token without an initialized MCP session can return `400 Missing session ID`; that indicates the request passed authentication and failed at protocol sequencing instead.

## Auth0 Management API least privilege

The Conduit `conduit:admin` scope is not an Auth0 Management API scope. The downstream M2M client used by `Auth0AdminClient` has its own Auth0 permissions.

Auth0 documents that `client_secret`, `client_authentication_methods`, signing keys, and related key material require `read:client_keys` or `read:client_credentials`, while ordinary client metadata can be retrieved with `read:clients`. citeturn3search1turn3search3

Therefore, granting a Conduit caller `conduit:admin` must not be interpreted as granting any of those sensitive Auth0 scopes.

## Local development

```json
{
  "mcpServers": {
    "conduit": {
      "command": "conduit",
      "args": ["--transport", "stdio"]
    }
  }
}
```

## Troubleshooting

### `401 invalid_token`

Check that the request contains:

```text
Authorization: Bearer <access-token>
```

### Token works at Auth0 but not Conduit

Verify the token's audience is exactly:

```text
https://conduit-mcp.onrender.com/mcp
```

and that the token includes `conduit:read`.

### Auth0 admin tool returns `Required scope: conduit:admin`

That is expected for a normal consumer token. Use a separately authorized administrative client only when the caller genuinely needs Conduit administration.

### `/health` works but `/mcp` does not

Expected: `/health` is a public liveness route while `/mcp` is the protected MCP resource.
