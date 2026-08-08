"""Unit tests for conduit.tools.files — no MCP dependency, no network."""

import pytest

from conduit.tools.files import Workspace, WorkspaceError


@pytest.fixture
def ws(tmp_path):
    return Workspace(tmp_path / "workspace")


def test_write_then_read_round_trips(ws):
    ws.write_file("a.txt", "hello conduit")
    assert ws.read_file("a.txt") == "hello conduit"


def test_write_refuses_to_clobber_without_overwrite(ws):
    ws.write_file("a.txt", "first")
    with pytest.raises(WorkspaceError):
        ws.write_file("a.txt", "second")
    assert ws.read_file("a.txt") == "first"


def test_write_overwrite_true_replaces(ws):
    ws.write_file("a.txt", "first")
    ws.write_file("a.txt", "second", overwrite=True)
    assert ws.read_file("a.txt") == "second"


def test_write_creates_parent_directories(ws):
    ws.write_file("nested/deep/file.txt", "content")
    assert ws.read_file("nested/deep/file.txt") == "content"


def test_read_missing_file_raises(ws):
    with pytest.raises(WorkspaceError):
        ws.read_file("missing.txt")


def test_read_oversized_file_raises(ws):
    ws.write_file("big.txt", "x" * 1000)
    with pytest.raises(WorkspaceError):
        ws.read_file("big.txt", max_bytes=100)


def test_relative_path_traversal_is_rejected(ws):
    ws.write_file("a.txt", "inside")
    with pytest.raises(WorkspaceError):
        ws.read_file("../a.txt")
    with pytest.raises(WorkspaceError):
        ws.read_file("../../etc/passwd")


def test_absolute_path_escape_is_rejected(ws):
    with pytest.raises(WorkspaceError):
        ws.read_file("/etc/passwd")


def test_list_directory(ws):
    ws.write_file("a.txt", "1")
    ws.write_file("sub/b.txt", "2")
    entries = ws.list_directory(".")
    names = {e["name"] for e in entries}
    assert names == {"a.txt", "sub"}
    kinds = {e["name"]: e["type"] for e in entries}
    assert kinds["sub"] == "directory"
    assert kinds["a.txt"] == "file"


def test_list_directory_on_missing_path_raises(ws):
    with pytest.raises(WorkspaceError):
        ws.list_directory("nope")


def test_search_finds_matches_case_insensitively(ws):
    ws.write_file("a.txt", "The Conduit routes tools.\nAnother line.")
    ws.write_file("b.txt", "conduit again")
    results = ws.search("CONDUIT")
    files_hit = {r["file"] for r in results}
    assert files_hit == {"a.txt", "b.txt"}


def test_search_reports_correct_line_numbers(ws):
    ws.write_file("a.txt", "one\ntwo\nmatch three\nfour")
    results = ws.search("match")
    assert len(results) == 1
    assert results[0]["line"] == 3


def test_search_respects_max_results(ws):
    for i in range(10):
        ws.write_file(f"f{i}.txt", "match here")
    results = ws.search("match", max_results=3)
    assert len(results) == 3


def test_search_empty_query_rejected(ws):
    with pytest.raises(WorkspaceError):
        ws.search("")


def test_workspace_creates_root_if_missing(tmp_path):
    root = tmp_path / "does" / "not" / "exist" / "yet"
    assert not root.exists()
    Workspace(root)
    assert root.is_dir()
