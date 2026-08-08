<div align="center">

# ⚡ Conduit MCP

### A serious MCP server for local tools and remote agents.

**One codebase · two transports · real OAuth · GitHub intelligence · resumable sessions**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-2.x-111827)](https://modelcontextprotocol.io/)
[![OAuth](https://img.shields.io/badge/Auth-OAuth%202.1-EB5424?logo=auth0&logoColor=white)](https://auth0.com/)
[![Render](https://img.shields.io/badge/Hosted%20on-Render-46E3B7?logo=render&logoColor=111827)](https://render.com/)

[**Live service**](https://conduit-mcp-nfmm.onrender.com/) · [**Health**](https://conduit-mcp-nfmm.onrender.com/health) · [**MCP endpoint**](https://conduit-mcp-nfmm.onrender.com/mcp) · [**Documentation site**](https://devxyi.github.io/conduit-mcp/) · [**GitHub**](https://github.com/devXyi/conduit-mcp)

</div>

---

## What is Conduit?

Conduit is a Python implementation of the **Model Context Protocol (MCP)** that gives AI agents a controlled workspace, live GitHub lookups, reusable prompts, and composed server-side workflows.

It exposes the same MCP server over two transport modes:

```text
                    ┌──────────────────────────┐
                    │       Conduit Core        │
                    │                          │
                    │ tools · prompts ·        │
                    │ resources · auth ·       │
                    │ resumability · security  │
                    └────────────┬─────────────┘
                                 │
                  ┌──────────────┴──────────────┐
                  │                             │
             local stdio                 Streamable HTTP
                  │                             │
          Claude / local agents          remote MCP clients
                                                │
                                           OAuth 2.1 / JWT
                                                │
                                              Auth0
```

The transport layer is intentionally thin: the MCP server and its tools stay shared, while `cli.py` decides how bytes move.

---

## ✨ Highlights

- **MCP-native** — tools, prompts, resources, and Streamable HTTP.
- **Two transports** — local `stdio` and network-facing HTTP from the same codebase.
- **OAuth 2.1 resource-server model** — Conduit verifies bearer JWTs; Auth0 issues them.
- **JWKS verification** — RS256 signatures, issuer, audience, expiry, `nbf`, `kid`, and required scopes.
- **Session resumability** — `Last-Event-ID` replay using an in-memory event store.
- **Sandboxed filesystem** — path traversal and absolute-path escapes are blocked.
- **GitHub intelligence** — repository metadata, repository search, user profiles, and composed research.
- **Prompt-injection boundary** — file content is explicitly treated as untrusted data.
- **Server-side composition** — `research_repo` orchestrates multiple operations concurrently.
- **Real integration tests** — including a real local JWKS server and authenticated MCP round trips.
- **Benchmarking** — transport and authentication overhead is measured rather than guessed.

---

## 🧰 Tools

| Tool | Purpose |
|---|---|
| `read_file(path)` | Read UTF-8 workspace content with an untrusted-content boundary |
| `write_file(path, content, overwrite=False)` | Create or update workspace files |
| `list_directory(path=".")` | List files and directories |
| `search_files(query, path=".")` | Case-insensitive workspace search with line numbers |
| `index_workspace(path=".")` | Hash files, report size/line counts, and detect exact duplicates |
| `github_repo_info(owner, repo)` | Live GitHub stars, forks, issues, language, and last-push data |
| `github_search_repos(query, limit=5)` | Search public GitHub repositories |
| `github_user_profile(username)` | Fetch a public GitHub profile summary |
| `research_repo(owner, repo)` | Composed repo research using GitHub + workspace data concurrently |

### MCP prompts

| Prompt | Arguments | Purpose |
|---|---|---|
| `/summarize_workspace_file` | `path` | Summarize a workspace file and surface an open question |
| `/repo_health_check` | `owner, repo` | Assess repository activity, popularity, and backlog |
| `/find_and_explain` | `query` | Search the workspace and explain relevant matches |

### Resource

```text
workspace://tree
```

A flat, browsable representation of the workspace tree.

---

## 🚀 Quickstart

### 1. Clone and install

```bash
git clone https://github.com/devXyi/conduit-mcp.git
cd conduit-mcp

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
```

### 2. Run locally over stdio

```bash
conduit --transport stdio
```

For Claude Desktop / compatible local MCP clients:

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

### 3. Run locally over HTTP

```bash
conduit --transport http --host 127.0.0.1 --port 8000
```

Then:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/health
http://127.0.0.1:8000/mcp
```

---

## 🌍 Live deployment

Conduit is currently deployed as a Python web service on Render.

| Endpoint | URL |
|---|---|
| **Service** | `https://conduit-mcp-nfmm.onrender.com/` |
| **Health** | `https://conduit-mcp-nfmm.onrender.com/health` |
| **MCP** | `https://conduit-mcp-nfmm.onrender.com/mcp` |
| **GitHub** | `https://github.com/devXyi/conduit-mcp` |
| **Docs / landing page** | `https://devxyi.github.io/conduit-mcp/` |

### Render configuration

The deployment is defined by [`render.yaml`](./render.yaml):

```yaml
services:
  - type: web
    name: conduit-mcp
    runtime: python
    plan: free
    buildCommand: pip install .
    startCommand: conduit --transport http --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
```

The deployed service has been validated to start Uvicorn, report `/health` as `200 OK`, and reject unauthenticated `/mcp` requests with an authentication error.

> **Free-tier note:** the Render instance can spin down after inactivity, so the first request after idle time may be slower.

---

## 🔐 OAuth 2.1 / Auth0

Conduit is an **OAuth resource server**, not an authorization server. It does not issue tokens or store user credentials. Auth0 handles token issuance; Conduit verifies the resulting JWT on protected MCP requests.

### Current Auth0 configuration

| Setting | Value |
|---|---|
| **Issuer** | `https://dev-jf6pbb4exdzatprm.eu.auth0.com/` |
| **JWKS** | `https://dev-jf6pbb4exdzatprm.eu.auth0.com/.well-known/jwks.json` |
| **API audience** | `https://conduit-mcp.onrender.com/mcp` |
| **Required scope** | `conduit:read` |
| **Application type** | Machine to Machine |
| **Token flow** | Client Credentials |

> **Important:** the Auth0 API audience is an OAuth resource identifier. It does not have to be identical to Render's current assigned hostname. In this deployment the Render URL is `https://conduit-mcp-nfmm.onrender.com`, while the configured Auth0 audience remains `https://conduit-mcp.onrender.com/mcp`.

### Environment variables

```bash
CONDUIT_AUTH_ISSUER=https://dev-jf6pbb4exdzatprm.eu.auth0.com/
CONDUIT_AUTH_AUDIENCE=https://conduit-mcp.onrender.com/mcp
CONDUIT_AUTH_JWKS_URL=https://dev-jf6pbb4exdzatprm.eu.auth0.com/.well-known/jwks.json
CONDUIT_AUTH_REQUIRED_SCOPES=conduit:read
```

For GitHub-backed tools:

```bash
GITHUB_TOKEN=<your-github-token>
```

**Never commit secrets to Git.** Use environment variables, `.env` locally, and Render's secret environment variables in deployment.

### What Conduit verifies

For protected HTTP requests, Conduit validates:

1. JWT signature against the issuer's JWKS.
2. `iss` against the configured issuer.
3. `aud` against the configured MCP resource audience.
4. `exp` / `nbf` timing claims.
5. `kid` selection when multiple signing keys are published.
6. Required OAuth scopes such as `conduit:read`.

This audience check is especially important for preventing a token minted for another resource from being replayed against Conduit.

### Unauthenticated behavior

The public health/status routes remain available for operational checks. The protected MCP endpoint requires a bearer token.

```text
GET /health
        │
        └── 200 OK

POST /mcp
        │
        ├── no token ───────────────→ 401 invalid_token
        │
        ├── wrong audience ─────────→ 401 invalid_token
        │
        └── valid Auth0 token ──────→ MCP session
```

---

## 🧪 Testing

Run the complete test suite:

```bash
pytest
```

Run unit/mocked tests without integration tests:

```bash
pytest -m "not integration"
```

The test suite covers:

- filesystem read/write/list/search
- path traversal and absolute-path escape attempts
- workspace indexing and duplicate detection
- composed-tool concurrency and partial failures
- untrusted-content wrapping
- resumability and event eviction
- JWT claims and scope mapping
- real RS256 JWKS verification
- key rotation and multi-key JWKS selection
- GitHub response mapping and errors
- real stdio subprocess communication
- real Streamable HTTP communication
- end-to-end OAuth enforcement

The most important end-to-end authentication test is:

```text
test_integration.py::test_http_transport_enforces_oauth_end_to_end
```

It validates the actual running Conduit server with:

```text
no token          → 401
wrong audience    → 401
valid JWT         → initialize → list tools → call tool
```

The local authorization-server fixture also mints real RS256 JWTs and exposes a real JWKS endpoint, including key rotation with an overlap window.

---

## ⚡ Benchmarks

Benchmarks use the same trivial `list_directory(".")` operation so the measurements focus on transport/protocol/auth overhead rather than tool complexity.

| Scenario | n | Mean | Median | p95 |
|---|---:|---:|---:|---:|
| In-process, no I/O | 30 | **0.69 ms** | 0.67 ms | 0.86 ms |
| stdio, fresh session/call | 10 | **1036.66 ms** | 1031.43 ms | 1101.65 ms |
| HTTP, sequential, no auth | 30 | **5.59 ms** | 5.43 ms | 6.85 ms |
| HTTP, 20 concurrent, no auth | 20 | **262.16 ms** | 274.53 ms | 301.71 ms |
| HTTP, sequential, with auth | 30 | **8.72 ms** | 5.88 ms | 46.34 ms |
| HTTP, 20 concurrent, with auth | 20 | **346.38 ms** | 375.40 ms | 386.37 ms |

### How to interpret this

- **In-process** is the protocol-dispatch floor.
- The large **fresh stdio** number is dominated by Python/process startup, not MCP itself.
- **HTTP** avoids repeated interpreter startup once a server is already running.
- Warm-JWKS authentication adds measurable but generally small sequential overhead in this benchmark.
- The concurrent scenarios create fresh sessions, so they measure connection/session setup under contention rather than sustained throughput.

Regenerate locally with:

```bash
python benchmarks/run_benchmarks.py
```

Treat the numbers above as directional measurements from the development environment, not lab-grade performance guarantees.

---

## 🛡️ Security model

Conduit treats two boundaries separately:

### Caller boundary

Remote HTTP callers may be untrusted. OAuth/JWT verification protects the MCP endpoint when authentication is configured.

### Content boundary

Workspace files and external GitHub content can contain adversarial text even when the caller is authenticated. File reads therefore cross an explicit untrusted-content boundary before reaching the model.

| Threat | Current status |
|---|---|
| Path traversal | ✅ Mitigated + tested |
| Absolute-path substitution | ✅ Mitigated + tested |
| Confused deputy / token passthrough | ✅ Audience check + end-to-end test |
| JWT signature / issuer / audience validation | ✅ Implemented + tested |
| Key rotation | ✅ Tested |
| Indirect prompt injection from full file content | 🟡 Partially mitigated |
| SSRF through shipped GitHub tool | ✅ Not applicable; destination is fixed |
| Unbounded `index_workspace` size | 🟡 Known limitation |
| Dynamic external tool registration | ❌ Not supported by design |
| Unauthenticated HTTP | 🟡 Protected when OAuth is enabled |

Conduit does **not** claim that server-side formatting can make prompt injection impossible. The security boundary is explicit about what it mitigates and what remains a model-level risk.

---

## 🧱 Project structure

```text
conduit-mcp/
├── src/conduit/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py             # transport + server startup
│   ├── server.py          # MCP server registration
│   ├── auth.py            # OAuth/JWT resource-server verification
│   ├── config.py          # configuration
│   ├── security.py        # untrusted-content boundaries
│   ├── resumability.py    # HTTP event store / replay
│   └── tools/
│       ├── files.py       # workspace operations
│       ├── github.py      # GitHub API client/tools
│       └── composed.py    # server-side research workflows
├── tests/
│   ├── test_auth.py
│   ├── test_security.py
│   ├── test_resumability.py
│   ├── test_tools_*.py
│   ├── test_integration.py
│   └── mock_auth_server.py
├── benchmarks/
├── render.yaml
├── pyproject.toml
└── README.md
```

---

## 🧠 Design principles

### One server, two transports

`server.py` creates one MCP server. The transport choice happens at the edge.

### Tools independent of MCP

Tool logic lives in ordinary Python functions. MCP decorators are thin bindings. This keeps business logic easy to unit test.

### Resource server, not identity provider

Conduit verifies tokens issued by an external authorization server. It intentionally does not implement `/oauth/token` or `/introspect`.

### Explicit security trade-offs

Security decisions are documented as threat-model decisions instead of being hidden behind vague claims like “secure by design.”

### Server-side composition

`research_repo` demonstrates the difference between an MCP prompt that asks the client/agent to orchestrate multiple calls and a composed tool that performs orchestration inside the server.

### Resumability with a deliberate scaling boundary

The current `InMemoryEventStore` is appropriate for a single-process deployment. Horizontal scaling would require a shared store such as Redis with consistent stream identity.

---

## 📦 Configuration

The project targets **Python 3.10+** and currently declares:

```text
mcp>=2.0.0
httpx>=0.28
python-dotenv>=1.0
pyjwt[crypto]>=2.10
```

Development dependencies include:

```text
pytest>=8.0
pytest-asyncio>=0.24
```

Common settings:

```bash
CONDUIT_HOST=127.0.0.1
CONDUIT_PORT=8000
CONDUIT_WORKSPACE=./workspace

# Optional GitHub access
GITHUB_TOKEN=<token>

# Optional HTTP authentication
CONDUIT_AUTH_ISSUER=<issuer>
CONDUIT_AUTH_AUDIENCE=<resource-audience>
CONDUIT_AUTH_JWKS_URL=<jwks-url>
CONDUIT_AUTH_REQUIRED_SCOPES=conduit:read
```

---

## 🗺️ Roadmap

- [x] MCP tools / prompts / resource
- [x] stdio transport
- [x] Streamable HTTP transport
- [x] Workspace sandboxing
- [x] GitHub integration
- [x] Server-side composed tool
- [x] Session resumability
- [x] OAuth/JWT verification
- [x] Auth0 integration
- [x] Real JWKS integration tests
- [x] Render deployment
- [x] Public health endpoint
- [x] Benchmark suite
- [ ] Production-grade shared event store for horizontal scaling
- [ ] Stronger resource-consumption limits for very large workspaces
- [ ] Broader integration coverage across MCP clients

---

## 📚 Learn more

- **Project site:** https://devxyi.github.io/conduit-mcp/
- **Repository:** https://github.com/devXyi/conduit-mcp
- **Live service:** https://conduit-mcp-nfmm.onrender.com/
- **MCP endpoint:** https://conduit-mcp-nfmm.onrender.com/mcp
- **Model Context Protocol:** https://modelcontextprotocol.io/
- **Auth0:** https://auth0.com/
- **Render:** https://render.com/

---

## ⚠️ Production notes

Conduit is currently a serious engineering project and working deployed service, but it should not be mistaken for a fully hardened multi-tenant production platform.

Before a high-risk production deployment, review at minimum:

- secret rotation and credential storage
- rate limiting and abuse controls
- workspace size/resource quotas
- distributed session/event storage
- observability and alerting
- deployment rollback strategy
- tenant isolation requirements
- GitHub token scope and rotation policy

---

## License

See the repository for the current project licensing terms.

---

<div align="center">

### Built to make MCP systems easier to build, test, secure, and deploy.

**Conduit MCP · one server · two transports · real security boundaries.**

</div>
