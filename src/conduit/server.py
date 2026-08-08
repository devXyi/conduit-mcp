"""The Conduit MCP server: tool, prompt, and resource definitions.

This module owns the single `MCPServer` instance. `conduit.cli` imports
`mcp` from here and runs it over whichever transport was requested. Every
tool below is a thin wrapper around a plain function in `conduit.tools` —
this module is the only place that imports `mcp` itself.
"""

from __future__ import annotations

from html import escape

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from mcp.server.mcpserver import Context, MCPServer

from .auth import build_auth
from .config import load_config
from .security import wrap_untrusted_content
from .tools.composed import research_repo as _research_repo
from .tools.files import Workspace
from .tools.github import GitHubClient

config = load_config()
workspace = Workspace(config.workspace_root)
github = GitHubClient(token=config.github_token)
_auth_settings, _token_verifier = build_auth(config.auth)

mcp = MCPServer(
    "conduit",
    title="Conduit",
    version="0.1.0",
    instructions=(
        "Conduit gives you a sandboxed local filesystem (read_file, write_file, "
        "list_directory, search_files) rooted at one workspace directory, plus "
        "live public GitHub lookups (github_repo_info, github_search_repos, "
        "github_user_profile). File paths are always relative to the workspace "
        "root; attempts to escape it are rejected."
    ),
    auth=_auth_settings,
    token_verifier=_token_verifier,
)


@mcp.tool()
def read_file(path: str) -> str:
    """Read a UTF-8 text file from the Conduit workspace."""
    content = workspace.read_file(path)
    return wrap_untrusted_content(content, source=f"workspace file '{path}'")


@mcp.tool()
def write_file(path: str, content: str, overwrite: bool = False) -> str:
    """Write a UTF-8 text file inside the Conduit workspace."""
    return workspace.write_file(path, content, overwrite=overwrite)


@mcp.tool()
def list_directory(path: str = ".") -> list[dict]:
    """List the files and subdirectories at a path inside the workspace."""
    return workspace.list_directory(path)


@mcp.tool()
async def search_files(query: str, path: str = ".", ctx: Context | None = None) -> list[dict]:
    """Search for a case-insensitive text match across workspace files."""
    if ctx is not None:
        await ctx.info(f"Searching '{path}' for '{query}'")
    return workspace.search(query, path)


@mcp.tool()
async def github_repo_info(owner: str, repo: str) -> dict:
    """Fetch live metadata for a public GitHub repository."""
    return await github.repo_info(owner, repo)


@mcp.tool()
async def github_search_repos(query: str, limit: int = 5) -> list[dict]:
    """Search public GitHub repositories."""
    return await github.search_repos(query, limit=limit)


@mcp.tool()
async def github_user_profile(username: str) -> dict:
    """Fetch a public GitHub user's profile summary."""
    return await github.user_profile(username)


@mcp.tool()
async def research_repo(owner: str, repo: str) -> dict:
    """Run the composed repository research operation."""
    return await _research_repo(github, workspace, owner, repo)


@mcp.tool()
async def index_workspace(path: str = ".", ctx: Context | None = None) -> dict:
    """Hash, size, and line-count every file in the workspace."""
    async def report(done: int, total: int) -> None:
        if ctx is not None:
            await ctx.report_progress(progress=done, total=total, message=f"Indexed {done}/{total} files")
    return await workspace.index(path, progress_cb=report)


@mcp.prompt()
def summarize_workspace_file(path: str) -> str:
    """Summarize a file from the workspace."""
    return (
        f"Read '{path}' with the read_file tool, then summarize it: the main "
        f"topic in one sentence, three to five key points as bullets, and one "
        f"open question the file leaves unanswered."
    )


@mcp.prompt()
def repo_health_check(owner: str, repo: str) -> str:
    """Assess a public GitHub repository's health from live data."""
    return (
        f"Call github_repo_info for '{owner}/{repo}'. Using pushed_at for "
        f"activity, the stars-to-forks ratio for popularity, and open_issues "
        f"for backlog size, give a one-line verdict — thriving, steady, or "
        f"stalled — with the three numbers that justify it."
    )


@mcp.prompt()
def find_and_explain(query: str) -> str:
    """Search the workspace and explain each match in context."""
    return (
        f"Call search_files for '{query}'. For every match, quote the line "
        f"and explain in one sentence why it's relevant to '{query}'."
    )


@mcp.resource("workspace://tree")
def workspace_tree() -> str:
    """A flat listing of every file currently in the Conduit workspace."""
    files = sorted(str(p.relative_to(workspace.root)) for p in workspace.root.rglob("*") if p.is_file())
    return "\n".join(files) or "(workspace is empty)"


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": mcp.name, "version": mcp.version})


@mcp.custom_route("/", methods=["GET"])
async def status_page(request: Request) -> HTMLResponse:
    tools = await mcp.list_tools()
    prompts = await mcp.list_prompts()
    return HTMLResponse(_render_status_page(tools, prompts, host=request.url.hostname or config.host, port=request.url.port or config.port))


def _render_status_page(tools, prompts, host: str, port: int) -> str:
    tool_items = "\n".join(
        f'''        <li class="row"><code class="name">{escape(t.name)}</code><span class="desc">{escape((t.description or "").strip().splitlines()[0] if t.description else "")}</span></li>'''
        for t in tools
    )
    prompt_items = "\n".join(
        f'''        <li class="row"><code class="name">/{escape(p.name)}</code><span class="desc">{escape((p.description or "").strip())}</span></li>'''
        for p in prompts
    )
    base_url = f"http://{host}:{port}"
    auth_on = config.auth is not None
    auth_badge = (
        '<div class="node accent"><span class="label">Auth</span><span class="value">OAuth 2.1 (Bearer)</span></div>'
        if auth_on else '<div class="node"><span class="label">Auth</span><span class="value">none</span></div>'
    )
    connect_note = (
        f'<p style="color: var(--muted); font-size: 13.5px; margin: 8px 0 0;">'
        f"Bearer token required on <code>/mcp</code> — issuer <code>{escape(config.auth.issuer)}</code>, "
        f"audience <code>{escape(config.auth.audience)}</code>. Metadata: "
        f'<a href="/.well-known/oauth-protected-resource">/.well-known/oauth-protected-resource</a></p>'
        if auth_on else ""
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Conduit — MCP server</title><style>
:root{{--ink:#101b2d;--panel:#16233b;--panel-line:rgba(235,231,218,.09);--paper:#ebe7da;--muted:#8c96ac;--copper:#c8935f;--verdigris:#74a89a;--mono:ui-monospace,SFMono,CascadiaCode,JetBrainsMono,Consolas,monospace;--sans:ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}}*{{box-sizing:border-box}}html{{background:var(--ink)}}body{{margin:0;background-color:var(--ink);background-image:linear-gradient(var(--panel-line) 1px,transparent 1px),linear-gradient(90deg,var(--panel-line) 1px,transparent 1px);background-size:28px 28px;color:var(--paper);font-family:var(--sans);line-height:1.55;min-height:100vh}}a{{color:var(--copper)}}.wrap{{max-width:880px;margin:0 auto;padding:56px 24px 80px}}.titleblock{{border:1px solid var(--panel-line);background:rgba(22,35,59,.6);padding:28px;margin-bottom:40px}}.eyebrow{{font-family:var(--mono);font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--verdigris);margin:0 0 10px}}h1{{font-family:var(--mono);font-size:clamp(32px,6vw,48px);letter-spacing:.02em;margin:0 0 12px}}.tagline{{color:var(--muted);max-width:60ch;margin:0;font-size:15px}}.flow{{display:flex;align-items:stretch;gap:0;margin:40px 0 48px;flex-wrap:wrap}}.node{{border:1px solid var(--panel-line);background:var(--panel);padding:16px 18px;font-family:var(--mono);font-size:13px;min-width:150px;flex:1 1 150px}}.node .label{{color:var(--muted);font-size:10px;letter-spacing:.12em;text-transform:uppercase;display:block;margin-bottom:6px}}.node .value{{color:var(--paper)}}.node.accent{{border-color:var(--copper)}}.node.accent .value{{color:var(--copper)}}.arrow{{display:flex;align-items:center;justify-content:center;color:var(--copper);font-family:var(--mono);padding:0 10px;flex:0 0 auto}}h2{{font-family:var(--mono);font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--verdigris);border-bottom:1px solid var(--panel-line);padding-bottom:10px;margin:40px 0 4px}}ul.list{{list-style:none;margin:0;padding:0}}li.row{{display:flex;gap:16px;align-items:baseline;padding:12px 2px;border-bottom:1px solid var(--panel-line)}}li.row .name{{font-family:var(--mono);color:var(--copper);font-size:13px;flex:0 0 auto;white-space:nowrap}}li.row .desc{{color:var(--muted);font-size:13.5px}}pre{{background:var(--panel);border:1px solid var(--panel-line);padding:16px 18px;overflow-x:auto;font-family:var(--mono);font-size:12.5px;color:var(--paper);margin:12px 0 0}}footer{{margin-top:56px;color:var(--muted);font-size:12px;font-family:var(--mono)}}
</style></head><body><div class="wrap"><div class="titleblock"><p class="eyebrow">MCP server · streamable-http</p><h1>CONDUIT</h1><p class="tagline">A conduit between AI agents and the outside world: a sandboxed local filesystem on one side, live public GitHub data on the other, one consistent tool interface between them. Running over stdio and Streamable HTTP from the same codebase.</p></div><div class="flow"><div class="node"><span class="label">Client</span><span class="value">AI agent</span></div><div class="arrow">→</div><div class="node accent"><span class="label">This server</span><span class="value">conduit v{escape(mcp.version)}</span></div><div class="arrow">→</div><div class="node"><span class="label">Local</span><span class="value">workspace/</span></div><div class="node"><span class="label">External</span><span class="value">api.github.com</span></div>{auth_badge}</div><h2>Tools ({len(tools)})</h2><ul class="list">{tool_items}</ul><h2>Commands ({len(prompts)})</h2><ul class="list">{prompt_items}</ul><h2>Connect</h2><p style="color:var(--muted);font-size:13.5px;margin:4px 0 0">stdio (Claude Desktop, Claude Code, most local agents) — add to your client's MCP config:</p><pre>{{
  "mcpServers": {{
    "conduit": {{
      "command": "conduit",
      "args": ["--transport", "stdio"]
    }}
  }}
}}</pre><p style="color:var(--muted);font-size:13.5px;margin:20px 0 0">Streamable HTTP (this server, right now):</p><pre>curl {escape(base_url)}/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{{"jsonrpc":"2.0","id":1,"method":"tools/list"}}'</pre>{connect_note}<footer>GET /health for a liveness check · POST /mcp for the MCP protocol endpoint</footer></div></body></html>"""
