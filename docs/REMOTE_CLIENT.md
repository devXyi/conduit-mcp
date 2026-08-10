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
      +--> Auth0 admin tools (deployment-controlled)
```

Conduit is the OAuth **resource server**. Auth0 is the authorization server.

## 1. Create an Auth0 Machine-to-Machine application

In the Auth0 tenant, create a Machine-to-Machine application for your own integration.

Authorize that application to the Conduit API with the scope:

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

The audience above is the configured OAuth resource identifier. It is intentionally separate from Render's assigned hostname (`conduit-mcp-nfmm.onrender.com`).

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
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
```

Never paste a client secret or access token into source control, README files, screenshots, or public issues.

## 3. Call a protected Conduit endpoint

A simple authenticated request to the MCP endpoint should include the bearer token:

```bash
curl -i "https://conduit-mcp-nfmm.onrender.com/mcp" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/json, text/event-stream"
```

Opening `/mcp` in a normal browser without a token is expected to produce an authentication error. That does **not** mean the server is down.

## 4. Connect from an MCP client

For an MCP client that supports remote Streamable HTTP plus OAuth, use:

```text
https://conduit-mcp-nfmm.onrender.com/mcp
```

The client should discover the protected-resource metadata and obtain an access token for the configured audience. Client-specific UI varies, so do not put a Conduit client secret into a shared MCP configuration.

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

## What a successful integration looks like

```text
GET  /health
     -> 200 OK

POST /mcp without token
     -> 401 invalid_token

POST /mcp with token for another audience
     -> 401 invalid_token

POST /mcp with valid Auth0 token + conduit:read
     -> authenticated MCP session
     -> tools/list
     -> tool calls
```

## Current remote tool surface

The deployed server currently exposes the core Conduit workspace/GitHub tools plus the narrowly scoped Auth0 Management API tools:

- `read_file`
- `write_file`
- `list_directory`
- `search_files`
- `index_workspace`
- `github_repo_info`
- `github_search_repos`
- `github_user_profile`
- `research_repo`
- `auth0_list_applications`
- `auth0_get_application`

The Auth0 Management API credentials belong to the **Conduit deployment**, not to remote consumers. Remote consumers only receive the capabilities exposed through Conduit's MCP tool layer.

## Security boundary

Conduit validates the caller's JWT before allowing protected MCP access. It checks the signing key through JWKS and validates issuer, audience, time claims, key ID, and required scopes.

GitHub and workspace content should still be treated as potentially untrusted text. Authentication proves who called Conduit; it does not make external content trustworthy.

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

### `/health` works but `/mcp` does not

That is normal when authentication is enabled. `/health` is intentionally a liveness/status route; `/mcp` is the protected MCP resource.
