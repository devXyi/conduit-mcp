<div align="center">

# ⚡ Conduit MCP

### A remote-ready MCP gateway for AI agents.

**One codebase · two transports · OAuth-protected HTTP · GitHub intelligence · sandboxed tools**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-2.x-111827)](https://modelcontextprotocol.io/)
[![OAuth](https://img.shields.io/badge/Auth-OAuth%202.1-EB5424?logo=auth0&logoColor=white)](https://auth0.com/)
[![Render](https://img.shields.io/badge/Hosted%20on-Render-46E3B7?logo=render&logoColor=111827)](https://render.com/)

[**Live service**](https://conduit-mcp-nfmm.onrender.com/) · [**Health**](https://conduit-mcp-nfmm.onrender.com/health) · [**MCP**](https://conduit-mcp-nfmm.onrender.com/mcp) · [**Docs**](https://devxyi.github.io/conduit-mcp/) · [**GitHub**](https://github.com/devXyi/conduit-mcp)

</div>

---

## What is Conduit?

Conduit is a Python implementation of the **Model Context Protocol (MCP)** that gives AI agents controlled access to a sandboxed workspace and live public GitHub lookups.

It runs the same MCP server over **local stdio** or **remote Streamable HTTP**.

```text
                         AI agent / MCP client
                                  │
                     ┌────────────┴────────────┐
                     │                         │
                  local                    remote
                   stdio                 Streamable HTTP
                     │                         │
                     ▼                         ▼
                ┌──────────────────────────────────┐
                │             CONDUIT               │
                │ MCP server · tools · security    │
                └───────────────┬──────────────────┘
                                │
                  ┌─────────────┴─────────────┐
                  ▼                           ▼
              Workspace                    GitHub
                tools                       tools

                         OAuth / JWT boundary
                                │
                              Auth0
```

**Security boundary:** Conduit's public MCP surface deliberately excludes Auth0 Management API operations. Server-side Auth0 Management API credentials, if configured for internal operations, are not delegated to MCP callers.

---

## 🟢 Live integration status

Conduit v0.1.0 has been validated end-to-end against the deployed Render service with a **separate Auth0 Machine-to-Machine client**.

```text
Auth0 Client Credentials
        ↓
Bearer access token
        ↓
Conduit /mcp
        ↓
MCP initialize
        ↓
notifications/initialized
        ↓
tools/list
        ↓
tools/call
        ↓
github_repo_info
        ↓
GitHub repository metadata returned
```

The remote test successfully returned `HTTP 200`, negotiated MCP protocol `2025-06-18`, discovered the public tool surface, and executed `github_repo_info` against `devXyi/conduit-mcp` with `isError: false`.

This is an integration proof, not a synthetic health check.

---

## ✨ Highlights

- **MCP-native** — tools, prompts, resources, and Streamable HTTP.
- **Two transports** — local `stdio` and network-facing HTTP from the same codebase.
- **OAuth 2.1 resource-server model** — Conduit verifies bearer JWTs; Auth0 issues them.
- **JWKS verification** — signature, issuer, audience, expiry, `nbf`, `kid`, and required scopes.
- **Resumable HTTP sessions** — bounded event replay using `Last-Event-ID`.
- **Sandboxed filesystem** — traversal and absolute-path escapes are blocked.
- **GitHub intelligence** — repository metadata, search, profiles, and composed research.
- **Untrusted-content boundary** — external text is treated as data, not trusted instructions.
- **Internal credential isolation** — Auth0 Management API credentials are not exposed as MCP tools.
- **Real integration tests** — authenticated MCP round trips, local JWKS, key rotation, and protocol behavior.
- **Reproducible benchmarks** — transport and authentication overhead is measured rather than guessed.

---

## 🧰 Public MCP tool surface

| Category | Tool | Purpose |
|---|---|---|
| Workspace | `read_file` | Read a UTF-8 file inside the workspace sandbox |
| Workspace | `write_file` | Write a UTF-8 file inside the workspace sandbox |
| Workspace | `list_directory` | List files/directories |
| Workspace | `search_files` | Case-insensitive text search |
| Workspace | `index_workspace` | Hash files, sizes, line counts, and duplicate detection |
| GitHub | `github_repo_info` | Live public repository metadata |
| GitHub | `github_search_repos` | Search public repositories |
| GitHub | `github_user_profile` | Public GitHub profile summary |
| GitHub | `research_repo` | Composed repository research workflow |

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

---

## 🚀 Use the hosted Conduit

Production MCP endpoint:

```text
https://conduit-mcp-nfmm.onrender.com/mcp
```

The HTTP endpoint is OAuth-protected. `/health` is public for liveness checks.

### Remote client model

Each consuming application should use **its own Auth0 credentials**. Never distribute Conduit's server-side Auth0 Management API secret.

```text
Your application
      │
      │ Client Credentials
      ▼
    Auth0
      │
      │ access token for Conduit
      ▼
  Conduit MCP
      │
      ├── Workspace
      └── GitHub
```

See [`docs/REMOTE_CLIENT.md`](./docs/REMOTE_CLIENT.md) for the complete remote setup and troubleshooting guide.

### Current Conduit OAuth configuration

```text
Issuer:
https://dev-jf6pbb4exdzatprm.eu.auth0.com/

API audience:
https://conduit-mcp.onrender.com/mcp

Required scope:
conduit:read
```

The OAuth audience is a resource identifier and is intentionally separate from Render's assigned hostname.

### MCP session sequence

A remote Streamable HTTP client should perform:

```text
1. obtain Auth0 access token
2. initialize MCP session
3. keep the returned Mcp-Session-Id
4. send notifications/initialized
5. call tools/list or tools/call
```

Opening `/mcp` in a normal browser without a bearer token is expected to fail. A valid token without a valid MCP session can instead return an MCP `400 Missing session ID`; that means authentication passed and the remaining issue is protocol sequencing.

---

## 🔐 Security model

Conduit separates **caller authentication** from **content trust** and **server credential trust**.

### Caller boundary

Remote HTTP callers are authenticated using OAuth/JWT. Conduit validates:

1. JWT signature against JWKS.
2. `iss` against the configured issuer.
3. `aud` against the configured resource audience.
4. `exp` and `nbf` timing claims.
5. `kid` for signing-key selection.
6. Required scopes such as `conduit:read`.

### Content boundary

Workspace files and GitHub responses can contain adversarial text even when the caller is authenticated. Authentication does not make external content trustworthy.

### Server credential boundary

Auth0 Management API credentials are a **deployment-side credential**, not a Conduit MCP capability. The public MCP server does not register Auth0 application-management tools. A token carrying `conduit:read` therefore cannot discover or invoke Auth0 Management API operations.

This is intentional: a general-purpose Conduit caller should not inherit the server's administrative authority merely because the server itself possesses a Management API credential.

### Auth0 Management API least privilege

If internal Auth0 administration is enabled elsewhere in the deployment, the Management API M2M application should receive only the scopes required by that internal operation. In particular, Auth0 documents that `client_secret` and other client key material require `read:client_keys` or `read:client_credentials`; Conduit should not grant those scopes merely to perform ordinary application metadata reads. citeturn3search0turn3search7

### Current threat posture

| Threat | Status |
|---|---|
| Path traversal | ✅ Mitigated + tested |
| Absolute-path escape | ✅ Mitigated + tested |
| JWT signature/issuer/audience validation | ✅ Implemented + tested |
| Key rotation | ✅ Tested |
| Confused-deputy audience mismatch | ✅ Tested |
| Auth0 admin tools exposed to `conduit:read` callers | ✅ Removed from public MCP surface |
| Server-side Auth0 credentials delegated to callers | ✅ Not exposed through MCP |
| Indirect prompt injection | 🟡 Partially mitigated; remains a model-level risk |
| Unbounded workspace indexing | 🟡 Known limitation |
| Dynamic external tool registration | ❌ Not supported by design |

**Never commit secrets.** Use local environment variables or `.env` files that are ignored by Git, and Render secret environment variables in deployment.

### Security regression test

The repository contains `tests/test_public_tool_surface.py`, which asserts that the Auth0 application-management tools are absent from the MCP tool list. This protects the credential/trust boundary against accidental re-registration.

---

## 🧪 Tests and CI

Run everything locally:

```bash
pytest
```

Unit/mocked tests:

```bash
pytest -m "not integration"
```

The suite covers filesystem boundaries, GitHub behavior, composed workflows, JWT claims, real RS256 JWKS verification, key rotation, stdio communication, Streamable HTTP, OAuth enforcement, and the public-tool security boundary.

Critical authentication flow:

```text
no token        → 401
wrong audience  → 401
valid JWT       → initialize → tools/list → tools/call
```

---

## ⚡ Benchmarks

The benchmark suite measures the same trivial `list_directory(".")` operation to isolate transport/protocol/auth overhead.

Current reference run:

| Scenario | n | Mean | Median | p95 |
|---|---:|---:|---:|---:|
| In-process, no I/O | 30 | **0.69 ms** | 0.67 ms | 0.86 ms |
| stdio, fresh session/call | 10 | **1036.66 ms** | 1031.43 ms | 1101.65 ms |
| HTTP, sequential, no auth | 30 | **5.59 ms** | 5.43 ms | 6.85 ms |
| HTTP, 20 concurrent, no auth | 20 | **262.16 ms** | 274.53 ms | 301.71 ms |
| HTTP, sequential, auth | 30 | **8.72 ms** | 5.88 ms | 46.34 ms |
| HTTP, 20 concurrent, auth | 20 | **346.38 ms** | 375.40 ms | 386.37 ms |

Regenerate with:

```bash
python benchmarks/run_benchmarks.py
```

The benchmark writes `benchmarks/results.md`. Numbers are directional measurements from the development environment, not performance guarantees.

---

## 📊 Remote smoke test

For a deployed environment, the most useful verification is protocol-level rather than `/health` alone:

```text
Auth0 token
   ↓
POST /mcp + Bearer token
   ↓
initialize → 200
   ↓
notifications/initialized → 202
   ↓
tools/list → 200
   ↓
tools/call → 200 + isError:false
```

The live Render deployment has completed this sequence with a separate external Auth0 client and a real `github_repo_info` invocation.

---

## 🌍 Deployment

The service is defined in [`render.yaml`](./render.yaml).

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

Current endpoints:

| Endpoint | URL |
|---|---|
| Service | `https://conduit-mcp-nfmm.onrender.com/` |
| Health | `https://conduit-mcp-nfmm.onrender.com/health` |
| MCP | `https://conduit-mcp-nfmm.onrender.com/mcp` |
| Documentation | `https://devxyi.github.io/conduit-mcp/` |

> Render's free tier may spin down after inactivity. A cold request can therefore take longer than a warm request.

---

## 🧱 Project structure

```text
conduit-mcp/
├── src/conduit/
│   ├── cli.py
│   ├── server.py
│   ├── auth.py
│   ├── auth0_admin.py       # internal client; NOT an MCP tool surface
│   ├── config.py
│   ├── security.py
│   ├── resumability.py
│   └── tools/
│       ├── files.py
│       ├── github.py
│       └── composed.py
├── tests/
│   ├── test_auth.py
│   ├── test_auth0_admin.py
│   ├── test_public_tool_surface.py
│   ├── test_integration.py
│   └── mock_auth_server.py
├── benchmarks/
│   ├── run_benchmarks.py
│   └── results.md
├── docs/
│   ├── index.html
│   └── REMOTE_CLIENT.md
├── examples/
│   └── remote_auth0_token.sh
├── render.yaml
├── pyproject.toml
└── README.md
```

---

## 🧠 Design principles

### One server, two transports

The MCP server and public tools are shared. Transport selection happens at the edge.

### Resource server, not identity provider

Conduit verifies tokens issued by an external authorization server. It does not issue credentials.

### Least privilege

Remote consumers receive only the public Conduit capabilities. Deployment-side Auth0 credentials are kept outside the MCP capability model.

### Explicit security trade-offs

Threat-model limitations are documented instead of hidden behind generic security claims.

### Server-side composition

`research_repo` demonstrates server-side orchestration, reducing round trips and keeping composed workflows behind a single MCP capability.

### Deliberate scaling boundary

The current in-memory event store is appropriate for a single process. Horizontal scaling will require shared event/session state such as Redis.

---

## 🗺️ Roadmap

### v0.1 — Core remote MCP

- [x] Local stdio transport
- [x] Streamable HTTP transport
- [x] OAuth/JWT resource-server authentication
- [x] Auth0 integration
- [x] GitHub tools
- [x] Sandboxed workspace tools
- [x] Session resumability
- [x] Remote external-client validation
- [x] Public MCP credential/trust boundary hardened
- [x] Regression test preventing Auth0 admin tool exposure

### Next

- [ ] Granular capability scopes (`conduit:github:read`, `conduit:workspace:write`, etc.) for the public tool surface
- [ ] Automated live MCP smoke test in release checks
- [ ] Custom production domain
- [ ] Better observability and request metrics
- [ ] Broader GitHub read capabilities
- [ ] Security hardening audit
- [ ] Public v0.1.0 release notes and MCP-directory distribution

---

## 📄 License

See [`LICENSE`](./LICENSE).

<div align="center">

**Conduit — a controlled conduit between AI agents and external capabilities.**

</div>
