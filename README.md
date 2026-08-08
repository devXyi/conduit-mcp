Conduit
An MCP server that gives AI agents a sandboxed local filesystem and live GitHub lookups — over stdio and Streamable HTTP, with OAuth 2.1, session resumability, and server-side tool composition — from one codebase.
Conduit implements the Model Context Protocol: tools, three "built-in commands" (MCP prompts), one browsable resource, and (when configured) OAuth-protected access, all served identically whether a client talks to it over stdio (Claude Desktop, Claude Code, most local agents) or over the network (Streamable HTTP).
$ conduit --transport stdio                  # local, subprocess-piped
$ conduit --transport http --port 8000       # network-reachable, visit http://localhost:8000
Architecture
flowchart LR
    subgraph Client["MCP Client"]
        Agent["AI agent"]
    end

    subgraph Conduit["Conduit"]
        direction TB
        CLI["cli.py — transport + event_store"]
        Server["server.py — tools · prompts · resource"]
        Auth["auth.py — OAuth 2.1 Resource Server"]
        Resume["resumability.py — EventStore"]
        Security["security.py — untrusted-content wrapping"]
        Files["tools/files.py — Workspace"]
        GH["tools/github.py — GitHubClient"]
        Composed["tools/composed.py — research_repo"]
        CLI --> Server
        Server --> Auth
        Server --> Security
        Server --> Files
        Server --> GH
        Server --> Composed
        Composed --> Files
        Composed --> GH
    end

    Agent -- "stdio, or Streamable HTTP\n+ Bearer token if auth is on" --> CLI
    Files --> FS[("local filesystem\nworkspace/")]
    GH --> API[("api.github.com")]
    Auth -. "verifies against" .-> IdP[("external Authorization Server\n(JWKS)")]
One binding layer, every transport. cli.py is the only place that decides how bytes move. server.py builds a single MCPServer and registers every tool, prompt, and resource on it once; mcp.run(transport=...) is what changes between stdio and HTTP.
Tools stay independent of MCP. Every tool in server.py is a thin wrapper around a plain function in tools/, auth.py, or resumability.py — none of which import mcp themselves. That split is what makes the whole system unit-testable with ordinary pytest fixtures; see Testing.
Quickstart
git clone <this-repo> conduit-mcp && cd conduit-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

conduit --transport stdio          # talk to it via any stdio MCP client
# or
conduit --transport http --port 8000   # then open http://127.0.0.1:8000
No configuration is required. Copy .env.example to .env to point at a different workspace, add a GITHUB_TOKEN, or turn auth on.
Connect from Claude Desktop / Claude Code
{
  "mcpServers": {
    "conduit": { "command": "conduit", "args": ["--transport", "stdio"] }
  }
}
See claude_desktop_config.example.json. Visiting http://127.0.0.1:8000/ while running in HTTP mode renders a status page listing every tool and command live from the running server.
Tools
Tool
What it does
read_file(path)
Read a UTF-8 text file from the workspace — wrapped in an untrusted-content boundary (see Threat model)
write_file(path, content, overwrite=False)
Write a file, creating parent directories as needed
list_directory(path=".")
List files and subdirectories at a path
search_files(query, path=".")
Case-insensitive text search across the workspace, with line numbers
index_workspace(path=".")
Hash, size, and line-count every file; flag exact duplicates — reports real progress as it goes
github_repo_info(owner, repo)
Live stars, forks, open issues, language, last-push date
github_search_repos(query, limit=5)
Search public GitHub repositories
github_user_profile(username)
A public user's profile summary
research_repo(owner, repo)
Composed: repo info + comparable repos + workspace mentions, concurrently, in one call
Commands (MCP prompts)
The "built-in commands" a connected client surfaces in its slash-command / input-box picker:
Command
Arguments
What it asks the agent to do
/summarize_workspace_file
path
Read a file and summarize: topic, key points, one open question
/repo_health_check
owner, repo
Fetch a repo and verdict its health from activity/popularity/backlog
/find_and_explain
query
Search the workspace and explain why each match is relevant
Note the difference from research_repo: a prompt tells the agent which tools to call in what order — one round trip per step, client-side. A composed tool does the orchestration itself, server-side, in one round trip.
Resource
workspace://tree — a flat text listing of every file in the workspace.
Auth (OAuth 2.1, optional)
Conduit acts as an OAuth 2.1 Resource Server only, per the MCP Authorization spec — it never issues tokens, runs a login page, or stores credentials. Point it at a real Authorization Server (Auth0, Okta, WorkOS, Keycloak, ...) and it verifies bearer tokens on every /mcp request; leave it unconfigured and /mcp behaves exactly as if auth code didn't exist.
CONDUIT_AUTH_ISSUER=https://your-tenant.us.auth0.com/
CONDUIT_AUTH_AUDIENCE=https://your-conduit-host/mcp   # set explicitly for real deployments
What's actually checked on every request, and why:
Signature — against the issuer's JWKS (RS256), cached in-process by kid.
exp/nbf — standard expiry.
iss — must equal the configured issuer exactly.
aud — must contain this server's resource URL (RFC 8707). This is the check that stops a token minted for a different MCP server from being replayed against this one — the "confused deputy" case RFC 8707 exists to prevent, and the detail that's easiest to skip if you copy a generic "verify a JWT" snippet instead of reading the MCP spec. Proven with a real test: test_wrong_audience_is_rejected.
/health and / stay public even with auth on — MCPServer.custom_route routes are exempt by design, appropriate for a liveness check and a status page, and confirmed by test_http_transport_enforces_oauth_end_to_end alongside the two rejection cases above.
Tested against a real local Authorization Server, not a mock of the verifier itself: tests/mock_auth_server.py runs a real Starlette+uvicorn app that mints real RS256 JWTs and serves a real JWKS endpoint, including key rotation with an overlap window — rotate_key() retires the old key but keeps it published for a grace period so already-issued tokens keep verifying, sweep_expired_keys() drops it once that window passes, and the JWKS response naturally contains multiple keys during the overlap (proving JWKSTokenVerifier picks the right one by kid out of several, not just the only one it's ever seen). Deliberately not built: /oauth/token and /introspect — a real grant flow needs authorization codes, PKCE, and client registration, which is a second project and not one Conduit's resource-server role needs, since Conduit only ever verifies tokens, never issues them.
Session resumability
Streamable HTTP can drop mid-response. Per spec, a reconnecting client resends the ID of the last event it saw via Last-Event-ID; a server wired up with an EventStore replays exactly what was missed. Conduit always runs with one (InMemoryEventStore, resumability.py) — an opt-in SDK feature that Conduit itself opts into unconditionally for the HTTP transport, with no behavior change for clients that never reconnect.
It's a bounded, per-stream, per-process log: correct for Conduit's single-process deployment, not for a horizontally-scaled one behind a load balancer (that would need Redis or similar, keyed the same way). Eviction is tested down to the exact boundary: replaying from an event whose own ID was already evicted still correctly returns everything newer than it (test_old_events_are_evicted_per_stream_cap), and stream-level LRU eviction is tested independently of event-level eviction (test_stream_count_is_capped_with_lru_eviction).
Threat model
Two different trust boundaries matter here: content flowing through Conduit (workspace files, GitHub responses) may be adversarial even when the caller is legitimate, and callers reaching the HTTP transport may be malicious unless auth is configured. What's below is organized around specific threats, not a generic checklist — each line is either mitigated and tested, or knowingly not mitigated, with the reasoning stated rather than left implicit.
Threat
Status
Notes
Path traversal (../, absolute-path substitution)
Mitigated, tested
Workspace._resolve + Path.relative_to; covers both vectors (see Design decisions)
Confused deputy / token passthrough
Mitigated, tested
RFC 8707 audience check, proven end-to-end against a real running server
Indirect prompt injection via tool output
Partially mitigated
read_file wraps content in an explicit data/instruction boundary (security.py). search_files snippets and GitHub free-text fields (description, bio) are not wrapped — a short quoted fragment is much lower "bandwidth" for a convincing injected instruction than an entire file, and wrapping every small field would be noise standing in for security. This is a mitigation, not a guarantee: test_a_fake_closing_tag_inside_the_content_does_not_relocate_the_real_boundary deliberately proves what it doesn't solve — a payload embedding its own fake closing tag is still just text a sufficiently adversarial model could be confused by; no server-side formatting can force model behavior.
SSRF via an external-API tool
Not applicable to the shipped tools
github.py's base_url is fixed to api.github.com, never agent- or user-supplied, so there's no attacker-controlled destination. Flagged here because it's the first thing to get wrong when adding a tool that takes a URL: it needs an explicit host allowlist, or an agent can be talked into making Conduit request internal/metadata endpoints (e.g. 169.254.169.254 on cloud hosts) on its behalf.
Unbounded resource consumption
Partially mitigated
read_file caps bytes read; search_files caps result count. index_workspace has no cap on workspace size — a many-GB workspace means a many-GB hash-everything call. Known gap, not yet fixed.
Tool/prompt description poisoning
Not applicable to Conduit's own tools
A malicious client-facing MCP server could ship a tool description containing injected instructions, which is a real, documented agentic-AI attack surface — but it's a client-trust problem, not something a server defends against in itself. Worth naming precisely because Conduit deliberately has no dynamic tool registration (see below): every description here is static and reviewed, not mutable at runtime by anything external.
Unauthenticated HTTP access
Mitigated when configured, tested
Opt-in OAuth (see Auth); off by default matches stdio's own model, where the MCP spec says credentials come from the environment, not the protocol.
Benchmarks
Real numbers, regenerable with python benchmarks/run_benchmarks.py (writes benchmarks/results.md). Every scenario calls the same trivial list_directory("."), so what's being measured is transport/protocol/auth overhead, not tool work. 3 warmup iterations discarded; 30 timed iterations (10 for stdio — each spawns a real process); 20 simultaneous sessions for the concurrent scenarios. Single run on shared, non-isolated hardware — the sandbox this was developed in — so treat these as directionally real, not lab-grade precise; rerun locally for numbers to actually cite.
Scenario
n
mean (ms)
median (ms)
p95 (ms)
min (ms)
max (ms)
in-process (no I/O)
30
0.69
0.67
0.86
0.60
0.91
stdio (fresh session/call)
10
1036.66
1031.43
1101.65
999.16
1101.65
HTTP, sequential, no auth
30
5.59
5.43
6.85
4.69
6.94
HTTP, 20 concurrent, no auth
20
262.16
274.53
301.71
146.95
301.79
HTTP, sequential, WITH auth
30
8.72
5.88
46.34
5.11
69.02
HTTP, 20 concurrent, WITH auth
20
346.38
375.40
386.37
211.43
386.42
What these actually show:
The in-process row is the floor — pure MCP dispatch, no subprocess, no socket: well under a millisecond.
stdio's cost is connection setup, not the call. ~1,037ms per fresh session is Python interpreter startup + subprocess spawn, roughly 1,500x the in-process floor — and it has nothing to do with MCP's protocol design. A long-lived stdio client that connects once and issues many calls doesn't pay this per call, only once.
HTTP amortizes that cost. Once a session exists, a sequential call over HTTP (5.6ms) is about 185x cheaper than a fresh stdio session, because it isn't paying for interpreter startup on every call.
Auth's per-call cost is small and bounded when the JWKS cache is warm: sequential mean goes from 5.59ms to 8.72ms — real, worth knowing, not free, but nowhere near dominating. The wider p95 (46ms vs. 6.85ms) is worth a second look rather than hand-waving; it wasn't investigated further here.
The concurrent numbers measure connection setup, not sustained throughput — each of the 20 "concurrent" samples opens a brand-new session (initialize + call), so ~275-350ms reflects 20 simultaneous fresh handshakes contending for the same process, not 20 calls on already-open connections. That's a real number, just a different question than "how fast is Conduit once warmed up" — worth being precise about which one is being asked.
Testing
pytest                          # everything
pytest -m "not integration"     # unit + mocked only — no network, no subprocesses, well under a second
File
What it proves
Needs?
test_tools_files.py
Workspace read/write/list/search, including path-escape security cases
Nothing
test_tools_index.py
index_workspace's hashing, duplicate detection, progress callback
Nothing
test_tools_composed.py
research_repo's concurrency and partial-failure isolation
Nothing (mocked GitHub)
test_security.py
Untrusted-content wrapping, including the boundary-spoofing limitation
Nothing
test_resumability.py
InMemoryEventStore: replay correctness, both eviction paths
Nothing
test_auth.py
Claims mapping (pure) + real JWKS verification, rotation, multi-key selection
Loopback only
test_tools_github_mocked.py
GitHub response-mapping and error handling, via httpx.MockTransport
Nothing
test_tools_github.py
The same client against the real API
GitHub (60/hr shared)
test_integration.py
Real MCP round trips: in-process, a real stdio subprocess, real Streamable HTTP, and the full OAuth flow through the actual running server (401 with no token, 401 with wrong audience, a real authenticated session)
GitHub + localhost
test_integration.py::test_http_transport_enforces_oauth_end_to_end is the one worth reading if you want proof the auth story isn't just JWKSTokenVerifier working in isolation: it spawns Conduit itself as a subprocess with auth configured via environment variables, mints tokens against a real local Authorization Server, and checks the actual HTTP responses — 401 with the right WWW-Authenticate header when unauthenticated, 401 for a wrong-audience token, and a full initialize + list_tools + call_tool round trip for a valid one.
On GitHub's rate limit: core (/repos/*, /users/*) and search are tracked separately — on a busy shared IP, core can be exhausted while search still works, which is why the composed-tool tests and the live integration test use search-backed calls. Set GITHUB_TOKEN to make every live test reliable regardless.
Design decisions
MCPServer, not FastMCP. The SDK this project pins (mcp>=2.0.0) renamed FastMCP to MCPServer and moved it to mcp.server.mcpserver; the decorator API (@mcp.tool(), @mcp.resource(), @mcp.prompt()) is unchanged. Verified against the installed package, not assumed from memory of older tutorials.
A module-level GitHubClient, not per-call or fully wired through lifespan. One httpx.AsyncClient reused for connection pooling. A multi-tenant deployment would move construction into MCPServer(lifespan=...) so it's scoped to server startup/shutdown; not needed at this scale, but the seam (server.py's module-level github = GitHubClient(...)) is there if this grows into one.
Composed tools live in tools/composed.py, not inline in server.py. Same reasoning as every other tool: the orchestration logic (asyncio.gather, per-leg error isolation) is real code worth unit testing without any MCP machinery involved, so it gets a plain async function and a thin @mcp.tool() wrapper, exactly like everything else.
Key rotation keeps the old key published, on purpose. The overlap window (grace_period_seconds) is what makes rotation not an outage — drop the old key immediately and every token issued in the seconds before rotation starts failing. sweep_expired_keys takes an explicit override so tests can force expiry deterministically instead of sleeping in real time.
read_file gets untrusted-content wrapping; search_files and GitHub's free-text fields don't. A whole file is far more "bandwidth" for a convincing injected instruction than an 80-character line or a bio field; wrapping everything turns a real defense into noise nobody reads. Stated as a trade-off, not hidden as an oversight — see Threat model.
Dynamic tool registration (notifications/tools/list_changed) was scoped out, not overlooked. The SDK supports it natively — ctx.notify_tools_changed() — so the protocol mechanism itself is a few lines. What's actually hard, and what a shipped version of this would need to get right, is how a new tool gets defined safely at runtime: a declarative, sandboxed spec (arguments, a whitelisted operation, no arbitrary code execution) rather than eval-ing anything external. That's a bigger design problem than the notification plumbing around it, and building a thin, unsafe version of it to check a box would be a worse artifact than not building it — matching the same "not over buzz engineering" bar as everything else here.
Possible extensions
A safe, declarative dynamic-tool-registration layer (see above)
A cap on index_workspace's total bytes/files, matching read_file's existing max_bytes guard
Redis-backed EventStore for a horizontally-scaled deployment
Investigate the auth p95 tail noted in Benchmarks rather than just reporting it