"""Benchmarks for Conduit: real numbers, not claims.

Four scenarios isolate different costs:

  1. in-process    — MCP dispatch overhead alone.
  2. stdio          — one full session per call: subprocess + interpreter startup + handshake + tool call.
  3. http           — persistent connection, sequential calls, then fresh concurrent sessions.
  4. http+auth      — identical HTTP scenarios with OAuth/JWT verification enabled.

Run with: python benchmarks/run_benchmarks.py
Results are also written to benchmarks/results.md so README numbers can be regenerated.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from mcp.client import Client  # noqa: E402
from mcp.client.session import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

from mock_auth_server import MockAuthServer  # noqa: E402

WARMUP_ITERATIONS = 3
TIMED_ITERATIONS = 30
CONCURRENCY = 20


@dataclass
class Stats:
    label: str
    samples_ms: list[float]

    @property
    def mean(self) -> float:
        return statistics.mean(self.samples_ms)

    @property
    def median(self) -> float:
        return statistics.median(self.samples_ms)

    @property
    def p95(self) -> float:
        return statistics.quantiles(self.samples_ms, n=20)[18] if len(self.samples_ms) >= 20 else max(self.samples_ms)

    @property
    def p99(self) -> float:
        if len(self.samples_ms) < 100:
            return max(self.samples_ms)
        return statistics.quantiles(self.samples_ms, n=100)[98]

    def row(self) -> str:
        return (
            f"| {self.label} | {len(self.samples_ms)} | {self.mean:.2f} | "
            f"{self.median:.2f} | {self.p95:.2f} | {self.p99:.2f} | "
            f"{min(self.samples_ms):.2f} | {max(self.samples_ms):.2f} |"
        )


async def time_calls(label: str, n: int, call) -> Stats:
    samples = []
    for _ in range(n):
        start = time.perf_counter()
        await call()
        samples.append((time.perf_counter() - start) * 1000)
    return Stats(label, samples)


async def free_port() -> int:
    import socket
    from contextlib import closing

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def bench_in_process() -> Stats:
    from conduit.server import mcp as server

    async with Client(server) as client:
        for _ in range(WARMUP_ITERATIONS):
            await client.call_tool("list_directory", {"path": "."})
        return await time_calls(
            "in-process (no I/O)",
            TIMED_ITERATIONS,
            lambda: client.call_tool("list_directory", {"path": "."}),
        )


async def one_stdio_session_call() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "conduit", "--transport", "stdio"], cwd=str(PROJECT_ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("list_directory", {"path": "."})


async def bench_stdio() -> Stats:
    for _ in range(WARMUP_ITERATIONS):
        await one_stdio_session_call()
    return await time_calls("stdio (fresh session/call)", 10, one_stdio_session_call)


class HttpServerHandle:
    def __init__(self, proc, url: str):
        self.proc = proc
        self.url = url

    async def stop(self) -> None:
        self.proc.terminate()
        try:
            await asyncio.wait_for(self.proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            self.proc.kill()
            await self.proc.wait()


async def start_http_server(*, env_extra: dict | None = None) -> HttpServerHandle:
    port = await free_port()
    env = {**os.environ, **(env_extra or {})}
    if "CONDUIT_AUTH_ISSUER" in env and "CONDUIT_AUTH_AUDIENCE" not in env:
        env["CONDUIT_AUTH_AUDIENCE"] = f"http://127.0.0.1:{port}/mcp"
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "conduit",
        "--transport",
        "http",
        "--port",
        str(port),
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/mcp"
    for _ in range(50):
        await asyncio.sleep(0.1)
        try:
            async with httpx.AsyncClient() as probe:
                await probe.post(url, json={"jsonrpc": "2.0", "id": 0, "method": "ping"})
            break
        except httpx.TransportError:
            continue
    return HttpServerHandle(proc, url)


async def bench_http_sequential(url: str, http_client: httpx.AsyncClient, label: str) -> Stats:
    async with streamable_http_client(url, http_client=http_client) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for _ in range(WARMUP_ITERATIONS):
                await session.call_tool("list_directory", {"path": "."})
            return await time_calls(label, TIMED_ITERATIONS, lambda: session.call_tool("list_directory", {"path": "."}))


async def bench_http_concurrent(url: str, http_client_factory, label: str, n: int) -> Stats:
    async def one_call() -> float:
        async with streamable_http_client(url, http_client=http_client_factory()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                start = time.perf_counter()
                await session.call_tool("list_directory", {"path": "."})
                return (time.perf_counter() - start) * 1000

    samples = await asyncio.gather(*(one_call() for _ in range(n)))
    return Stats(label, list(samples))


async def main() -> None:
    results: list[Stats] = []

    print("Running in-process benchmark...")
    results.append(await bench_in_process())

    print("Running stdio benchmark (10 fresh subprocess sessions)...")
    results.append(await bench_stdio())

    print("Starting HTTP server (no auth)...")
    http = await start_http_server()
    try:
        results.append(await bench_http_sequential(http.url, httpx.AsyncClient(), "HTTP, sequential, no auth"))
        results.append(await bench_http_concurrent(http.url, httpx.AsyncClient, f"HTTP, {CONCURRENCY} concurrent, no auth", CONCURRENCY))
    finally:
        await http.stop()

    print("Starting mock Authorization Server + HTTP server with auth ON...")
    mock_as = MockAuthServer(issuer="https://bench-idp.example.test/")
    uv_config = uvicorn.Config(mock_as.app, host="127.0.0.1", port=0, log_level="warning")
    uv_server = uvicorn.Server(uv_config)
    as_task = asyncio.create_task(uv_server.serve())
    while not uv_server.started:
        await asyncio.sleep(0.01)
    as_port = uv_server.servers[0].sockets[0].getsockname()[1]
    jwks_url = f"http://127.0.0.1:{as_port}/jwks.json"

    authed_http = await start_http_server(
        env_extra={
            "CONDUIT_AUTH_ISSUER": mock_as.issuer,
            "CONDUIT_AUTH_JWKS_URL": jwks_url,
        }
    )
    try:
        token = mock_as.mint_token(audience=authed_http.url)
        authed_client_factory = lambda: httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"})  # noqa: E731
        results.append(await bench_http_sequential(authed_http.url, authed_client_factory(), "HTTP, sequential, WITH auth"))
        results.append(await bench_http_concurrent(authed_http.url, authed_client_factory, f"HTTP, {CONCURRENCY} concurrent, WITH auth", CONCURRENCY))
    finally:
        await authed_http.stop()
        uv_server.should_exit = True
        await as_task

    header = "| Scenario | n | mean (ms) | median (ms) | p95 (ms) | p99 (ms) | min (ms) | max (ms) |\n"
    header += "|---|---:|---:|---:|---:|---:|---:|---:|\n"
    table = header + "\n".join(r.row() for r in results)

    print("\n" + table + "\n")

    out_path = Path(__file__).parent / "results.md"
    out_path.write_text(
        "# Conduit benchmark results\n\n"
        f"Machine: {os.uname().sysname} {os.uname().machine}, Python {sys.version.split()[0]}\n\n"
        f"Warmup: {WARMUP_ITERATIONS} discarded iterations where applicable. "
        f"Timed iterations: {TIMED_ITERATIONS} (stdio: 10). Concurrent scenarios: {CONCURRENCY} simultaneous sessions.\n\n"
        "All calls are `list_directory(\".\")` against the same near-empty workspace, "
        "so every scenario is measuring transport/protocol/auth overhead, not tool work.\n\n"
        + table
        + "\n"
    )
    print(f"Results written to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
