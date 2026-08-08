"""Command-line entrypoint: `conduit` (after install) or `python -m conduit`.

    conduit --transport stdio             # for Claude Desktop, Claude Code, etc.
    conduit --transport http --port 8000  # for a network-reachable agent
"""

from __future__ import annotations

import argparse

from .resumability import InMemoryEventStore
from .server import config, mcp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="conduit", description="Run the Conduit MCP server.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="stdio for local MCP clients (default); http for a network-reachable server",
    )
    parser.add_argument("--host", default=config.host, help=f"HTTP bind host (default: {config.host})")
    parser.add_argument("--port", type=int, default=config.port, help=f"HTTP bind port (default: {config.port})")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            streamable_http_path="/mcp",
            event_store=InMemoryEventStore(),
        )


if __name__ == "__main__":
    main()
