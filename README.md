<div align="center">

# ⚡ Conduit MCP

### A remote-ready MCP gateway for AI agents.

**One codebase · two transports · OAuth-protected HTTP · GitHub intelligence · sandboxed tools**

[**Live service**](https://conduit-mcp-nfmm.onrender.com/) · [**Health**](https://conduit-mcp-nfmm.onrender.com/health) · [**MCP**](https://conduit-mcp-nfmm.onrender.com/mcp) · [**Docs**](https://devxyi.github.io/conduit-mcp/) · [**GitHub**](https://github.com/devXyi/conduit-mcp)

</div>

---

## What is Conduit?

Conduit is a Python implementation of the **Model Context Protocol (MCP)** that gives AI agents controlled access to a sandboxed workspace and live public GitHub lookups. It runs the same server over local **stdio** or remote **Streamable HTTP**.

```text
AI agent / MCP client
        │
        ├── stdio ───────────────┐
        │                         ▼
        └── OAuth + HTTP ───►  CONDUIT
                                │
                         ┌──────┴──────┐
                         ▼             ▼
                    Workspace       GitHub
                      tools          tools

Remote authentication: Auth0 → JWT → Conduit
Sensitive administration: conduit:admin → Auth0 admin tools
```

**Core security boundary:** `conduit:read` authenticates ordinary remote consumers. Auth0 Management API operations require the separate `conduit:admin` capability. The server-side Auth0 Management API credential is never itself treated as a caller capability.

---

## 🟢 Live integration

The deployed Render service has been validated with a separate Auth0 Machine-to-Machine client:

```text
Auth0 Client Credentials
        ↓
Bearer access token
        ↓
POST /mcp
        ↓
initialize → MCP session
        ↓
tools/list
        ↓
tools/call → github_repo_info
        ↓
real GitHub metadata · isError:false
```

This is a protocol-level integration proof rather than a `/health`-only check.

---

## 🧰 Tool surface

| Category | Tool | Required capability |
|---|---|---|
| Workspace | `read_file` | `conduit:read` |
| Workspace | `write_file` | `conduit:read` |
| Workspace | `list_directory` | `conduit:read` |
| Workspace | `search_files` | `conduit:read` |
| Workspace | `index_workspace` | `conduit:read` |
| GitHub | `github_repo_info` | `conduit:read` |
| GitHub | `github_search_repos` | `conduit:read` |
| GitHub | `github_user_profile` | `conduit:read` |
| GitHub | `research_repo` | `conduit:read` |
| Auth0 | `auth0_list_applications` | **`conduit:admin`** |
| Auth0 | `auth0_get_application` | **`conduit:admin`** |

The two Auth0 tools are deliberately capability-gated at invocation time. A valid `conduit:read` token cannot use them.

### MCP prompts

- `/summarize_workspace_file(path)`
- `/repo_health_check(owner, repo)`
- `/find_and_explain(query)`

### Resource

```text
workspace://tree
```

---

## 🚀 Remote use

Production endpoint:

```text
https://conduit-mcp-nfmm.onrender.com/mcp
```

The HTTP endpoint requires a bearer token. `/health` is public for liveness.

Each consuming application should use its **own Auth0 credentials**. Never distribute Conduit's server-side Management API secret.

Current resource configuration:

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

See [`docs/REMOTE_CLIENT.md`](./docs/REMOTE_CLIENT.md) for remote setup.

---

## 🔐 Security model

Conduit separates three trust domains:

### 1. Caller authentication

The HTTP resource server validates JWT signature, issuer, audience, expiry, `nbf`, `kid`, and the globally required scope. Auth0 issues the access token; Conduit verifies it. citeturn0search8turn0search2

### 2. Per-tool authorization

The global `conduit:read` check is intentionally not the complete authorization policy. Sensitive Auth0 tools call `require_scope(ctx, "conduit:admin")` immediately before any Management API request.

Therefore:

```text
Token scopes                 Result
────────────────────────────────────────────
conduit:read                 GitHub + workspace
conduit:read + conduit:admin GitHub + workspace + Auth0 admin
no conduit:read              rejected at resource boundary
```

This is a local Conduit capability boundary rather than relying on the downstream Auth0 Management API to provide the right tenant-level separation.

### 3. Deployment credential boundary

`AUTH0_CLIENT_SECRET` belongs only to the server-side Auth0 Management API client. A remote Conduit caller never receives it and never supplies it to the downstream Management API.

Auth0 documents that ordinary client properties such as callbacks and JWT configuration require `read:clients` (or `read:client_keys`), while sensitive properties including `client_secret`, `client_authentication_methods`, and signing keys specifically require `read:client_keys` or `read:client_credentials`. citeturn3search1turn3search3

**Least privilege therefore applies at both layers:** Conduit callers need `conduit:admin` for administrative tools, while the server's separate Auth0 M2M client should receive only the Management API scopes those tools actually need.

### Threat table

| Threat | Status |
|---|---|
| Path traversal / absolute-path escape | ✅ Mitigated + tested |
| JWT signature / issuer / audience validation | ✅ Implemented + tested |
| Key rotation | ✅ Tested |
| Confused deputy via audience mismatch | ✅ Tested |
| `conduit:read` invoking Auth0 admin tools | ✅ Blocked by per-tool `conduit:admin` check |
| Server-side Auth0 credential delegated to callers | ✅ Not exposed |
| Auth0 client-secret retrieval by Conduit caller | ✅ Requires `conduit:admin` **and** downstream Auth0 privilege; no `read:client_keys` implied |
| Indirect prompt injection | 🟡 Remains a model-level risk |
| Unbounded workspace indexing | 🟡 Known limitation |
| Dynamic external tool registration | ❌ Not supported by design |

**Never commit secrets.** Use environment variables / Render secret environment variables.

---

## 🧪 Tests

```bash
pytest
```

The security regression suite includes:

```text
conduit:read
     │
     └── auth0_get_application ──► InsufficientScopeError ❌

conduit:read + conduit:admin
     │
     └── auth0_get_application ──► authorization passes ✓
```

The test suite also covers filesystem boundaries, JWT claims, JWKS verification, key rotation, stdio, Streamable HTTP, OAuth enforcement, GitHub behavior, and composed workflows.

---

## ⚡ Benchmarks

Reference development-environment measurements for `list_directory(".")`:

| Scenario | Mean | Median | p95 |
|---|---:|---:|---:|
| In-process | **0.69 ms** | 0.67 ms | 0.86 ms |
| stdio, fresh session | **1036.66 ms** | 1031.43 ms | 1101.65 ms |
| HTTP, sequential, no auth | **5.59 ms** | 5.43 ms | 6.85 ms |
| HTTP, sequential, auth | **8.72 ms** | 5.88 ms | 46.34 ms |
| HTTP, 20 concurrent, auth | **346.38 ms** | 375.40 ms | 386.37 ms |

Regenerate with:

```bash
python benchmarks/run_benchmarks.py
```

These are directional measurements, not performance guarantees.

---

## 🌍 Deployment

The service is deployed from `main` with Render and exposes:

| Endpoint | URL |
|---|---|
| Service | `https://conduit-mcp-nfmm.onrender.com/` |
| Health | `https://conduit-mcp-nfmm.onrender.com/health` |
| MCP | `https://conduit-mcp-nfmm.onrender.com/mcp` |
| Docs | `https://devxyi.github.io/conduit-mcp/` |

Render's free tier may spin down after inactivity.

---

## 🧱 Project structure

```text
conduit-mcp/
├── src/conduit/
│   ├── cli.py
│   ├── server.py
│   ├── auth.py                 # JWT verification + per-tool scope helper
│   ├── auth0_admin.py          # server-side Management API client
│   ├── config.py
│   ├── security.py
│   └── tools/
│       ├── files.py
│       ├── github.py
│       └── composed.py
├── tests/
│   ├── test_auth.py
│   ├── test_auth0_admin.py
│   ├── test_public_tool_surface.py
│   ├── test_tool_scopes.py     # conduit:read vs conduit:admin
│   └── test_integration.py
├── docs/
│   ├── index.html
│   └── REMOTE_CLIENT.md
├── benchmarks/
├── render.yaml
├── pyproject.toml
└── README.md
```

---

## 🧠 Design principles

### One server, two transports

Transport changes how clients reach Conduit, not the underlying capability model.

### Resource server, not identity provider

Conduit verifies tokens issued by Auth0; it does not issue caller credentials.

### Least privilege at two boundaries

OAuth scopes protect the Conduit capability surface. Auth0 Management API scopes protect the downstream tenant administration surface.

### Authorization before delegation

The `conduit:admin` check occurs before an Auth0 Management API request is made. A `conduit:read` caller cannot reach the downstream credentialed client at all.

### Explicit threat model

Known limitations are documented rather than hidden behind generic security claims.

---

## 🗺️ Roadmap

### v0.1

- [x] Local stdio transport
- [x] Streamable HTTP
- [x] OAuth/JWT resource-server authentication
- [x] Auth0 integration
- [x] GitHub tools
- [x] Sandboxed workspace
- [x] Session resumability
- [x] Remote external-client validation
- [x] Auth0 admin capability boundary with `conduit:admin`
- [x] Regression tests for read/admin scope isolation

### Next

- [ ] Expand granular scopes (`conduit:github:read`, `conduit:workspace:write`, etc.)
- [ ] Filter `tools/list` by caller capability where supported by the server layer
- [ ] Automated live MCP smoke test in release checks
- [ ] Better observability and request metrics
- [ ] Security hardening audit
- [ ] Public v0.1.0 release notes and MCP-directory distribution

---

## 📄 License

See [`LICENSE`](./LICENSE).

<div align="center">

**Conduit — a controlled conduit between AI agents and external capabilities.**

</div>
