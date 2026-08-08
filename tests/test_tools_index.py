"""Tests for Workspace.index() — no MCP, no Context; progress_cb is just a
plain async callable here, proving the mechanism independent of the MCP
progress-notification plumbing that conduit.server wires it into."""

from __future__ import annotations

import hashlib

import pytest

from conduit.tools.files import Workspace


@pytest.fixture
def ws(tmp_path):
    return Workspace(tmp_path / "workspace")


async def test_index_reports_file_count_and_total_bytes(ws):
    ws.write_file("a.txt", "hello")
    ws.write_file("sub/b.txt", "world!")

    result = await ws.index()

    assert result["file_count"] == 2
    assert result["total_bytes"] == len("hello") + len("world!")


async def test_index_computes_correct_sha256_per_file(ws):
    ws.write_file("a.txt", "hello")

    result = await ws.index()

    entry = next(e for e in result["files"] if e["file"] == "a.txt")
    assert entry["sha256"] == hashlib.sha256(b"hello").hexdigest()


async def test_index_line_counts(ws):
    ws.write_file("no_trailing_newline.txt", "line1\nline2\nline3")  # 3 lines, no trailing \n
    ws.write_file("trailing_newline.txt", "line1\nline2\n")  # 2 lines, trailing \n
    ws.write_file("empty.txt", "")

    result = await ws.index()
    by_name = {e["file"]: e for e in result["files"]}

    assert by_name["no_trailing_newline.txt"]["lines"] == 3
    assert by_name["trailing_newline.txt"]["lines"] == 2
    assert by_name["empty.txt"]["lines"] == 0


async def test_index_flags_exact_duplicates(ws):
    ws.write_file("a.txt", "same content")
    ws.write_file("b.txt", "same content")
    ws.write_file("c.txt", "different content")

    result = await ws.index()

    assert len(result["duplicate_groups"]) == 1
    assert set(result["duplicate_groups"][0]) == {"a.txt", "b.txt"}


async def test_index_on_empty_workspace(ws):
    result = await ws.index()
    assert result == {"file_count": 0, "total_bytes": 0, "duplicate_groups": [], "files": []}


async def test_index_calls_progress_callback_once_per_file_in_order(ws):
    for i in range(5):
        ws.write_file(f"f{i}.txt", "x")

    calls: list[tuple[int, int]] = []

    async def record(done: int, total: int) -> None:
        calls.append((done, total))

    await ws.index(progress_cb=record)

    assert calls == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]


async def test_index_without_progress_callback_still_works(ws):
    ws.write_file("a.txt", "x")
    result = await ws.index(progress_cb=None)
    assert result["file_count"] == 1


async def test_index_respects_relative_path_scope(ws):
    ws.write_file("included/a.txt", "in scope")
    ws.write_file("excluded/b.txt", "out of scope")

    result = await ws.index("included")

    assert result["file_count"] == 1
    assert result["files"][0]["file"] == "included/a.txt"
