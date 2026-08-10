# Connect to Conduit remotely

Conduit can be consumed as a remote MCP server without cloning the repository or rebuilding the server.

## Production endpoints

- Service: `https://conduit-mcp-nfmm.onrender.com/`
- Health: `https://conduit-mcp-nfmm.onrender.com/health`
- MCP: `https://conduit-mcp-nfmm.onrender.com/mcp`
- Protected-resource metadata: `https://conduit-mcp-nfmm.onrender.com/.well-known/oauth-protected-resource`

The `/health` endpoint is public. `/mcp` is protected by OAuth and requires a bearer access token.

## Recommended integration model

Each consuming application should have **its own OAuth client credentials**. Do not give another developer Conduit's client secret.

```text
Your application
      |
      | Client Credentials
      v
    Auth0
      |
      | access_token
      v
Conduit MCP
      |
      +--> workspace tools
      +--> GitHub tools
```

Conduit is the OAuth **resource server**. Auth0 is the authorization server.

**Important security boundary:** Auth0 Management API credentials, if present in the Conduit deployment for internal operations, are not exposed as MCP tools. A remote caller with `conduit:read` cannot inherit the deployment's Auth0 administrative authority.

## 1. Create an Auth0 Machine-to-Machine application

In the Auth0 tenant, create a Machine-to-Machine application for your own integration.

Authorize that application to the Conduit API with:

```text
conduit:read
```

Current Conduit resource configuration:

```text
Issuer:
https://dev-jf6pbb4exdzatprm.eu.auth0.com/

Audience:
https://conduit-mcp.onrender.com/mcp

Scope:
conduit:read
```

The audience is the configured OAuth resource identifier and is intentionally separate from Render's assigned hostname.

## 2. Request an access token

Use your application's own `client_id` and `client_secret`.

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

Never paste a client secret or access token into source control, README files, screenshots, or public issues.

## 3. Connect from an MCP client

For an MCP client that supports remote Streamable HTTP plus OAuth, use:

```text
https://conduit-mcp-nfmm.onrender.com/mcp
```

The client should discover the protected-resource metadata and obtain an access token for the configured audience.

### Local development instead

If the consumer wants to run Conduit locally, stdio remains available:

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

## 4. Reproduce the full remote smoke test

```bash
export AUTH0_DOMAIN="dev-jf6pbb4exdzatprm.eu.auth0.com"
export CLIENT_ID="your-client-id"
export CLIENT_SECRET="your-client-secret"
export CONDUIT_URL="https://conduit-mcp-nfmm.onrender.com/mcp"
export CONDUIT_AUDIENCE="https://conduit-mcp.onrender.com/mcp"

bash examples/remote_mcp_smoke.sh
```

The script verifies:

```text
Auth0 token
    ↓
MCP initialize → 200
    ↓
notifications/initialized → 202
    ↓
tools/list → public Conduit tools
    ↓
tools/call → 200 + isError:false
```

It never prints the client secret or access token.

## Current public remote tool surface

- `read_file`
- `write_file`
- `list_directory`
- `search_files`
- `index_workspace`
- `github_repo_info`
- `github_search_repos`
- `github_user_profile`
- `research_repo`

Auth0 application-management operations are **not** part of this list. The repository contains an internal Auth0 Management API client, but it is deliberately not registered as an MCP tool.

## Security boundary

Conduit validates the caller's JWT before allowing protected MCP access. It checks the signing key through JWKS and validates issuer, audience, time claims, key ID, and required scopes.

Authentication proves who called Conduit; it does not make GitHub or workspace content trustworthy.

The deployment-side Auth0 Management API credential is a separate trust domain. It must not be treated as a capability granted to MCP callers.

Auth0 also documents that sensitive client key material such as `client_secret` requires `read:client_keys` or `read:client_credentials`, while ordinary client metadata uses less-privileged scopes. Internal Management API clients should therefore be granted only the minimum scopes needed for their specific backend operation. citeturn3search0turn3search7

## Troubleshooting

### `{"error":"invalid_token","error_description":"Authentication required"}`

You reached the protected MCP endpoint without a usable bearer token. Check that the request contains:

```text
Authorization: Bearer <access-token>
```

### Token works against Auth0 but not Conduit

Check that the token was requested with the exact Conduit audience:

```text
https://conduit-mcp.onrender.com/mcp
```

Also verify that the Auth0 application is authorized for the Conduit API and has `conduit:read`.

### `400 Bad Request: Missing session ID`

Authentication reached the MCP layer, but the request is missing the session established by `initialize`. Run `initialize`, capture the returned `mcp-session-id`, then send `notifications/initialized` and subsequent tool calls with that session ID.

### `/health` works but `/mcp` does not

That is normal when authentication is enabled. `/health` is intentionally a liveness/status route; `/mcp` is the protected MCP resource.
