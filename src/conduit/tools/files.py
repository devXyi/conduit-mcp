"""A sandboxed workspace for reading, writing, listing, and searching text files.

Every path a caller supplies is resolved relative to a workspace root and
checked against it with `Path.relative_to`, which is robust against both
`../` traversal and absolute-path substitution (`Path("/root") / "/etc/passwd"`
silently discards the base in a plain join, but the post-resolve containment
check below still catches it).
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

ProgressCallback = Callable[[int, int], Awaitable[None]]


class WorkspaceError(Exception):
    """Raised for any invalid, unsafe, or out-of-bounds workspace operation."""


@dataclass
class Workspace:
    root: Path

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            raise WorkspaceError(
                f"'{relative_path}' resolves outside the workspace root — refusing to touch it"
            ) from None
        return candidate

    def read_file(self, relative_path: str, max_bytes: int = 200_000) -> str:
        path = self._resolve(relative_path)
        if not path.is_file():
            raise WorkspaceError(f"No such file: '{relative_path}'")
        data = path.read_bytes()
        if len(data) > max_bytes:
            raise WorkspaceError(
                f"'{relative_path}' is {len(data):,} bytes, over the {max_bytes:,}-byte read limit"
            )
        return data.decode("utf-8", errors="replace")

    def write_file(self, relative_path: str, content: str, overwrite: bool = False) -> str:
        path = self._resolve(relative_path)
        if path.exists() and not overwrite:
            raise WorkspaceError(f"'{relative_path}' already exists — pass overwrite=true to replace it")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Wrote {len(content):,} characters to '{relative_path}'"

    def list_directory(self, relative_path: str = ".") -> list[dict]:
        path = self._resolve(relative_path)
        if not path.is_dir():
            raise WorkspaceError(f"Not a directory: '{relative_path}'")
        entries = []
        for child in sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            entries.append(
                {
                    "name": child.name,
                    "type": "directory" if child.is_dir() else "file",
                    "size_bytes": child.stat().st_size if child.is_file() else None,
                }
            )
        return entries

    def search(self, query: str, relative_path: str = ".", max_results: int = 50) -> list[dict]:
        if not query:
            raise WorkspaceError("Search query cannot be empty")
        root = self._resolve(relative_path)
        needle = query.lower()
        results: list[dict] = []
        for file_path in sorted(root.rglob("*")):
            if len(results) >= max_results:
                break
            if not file_path.is_file():
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if needle in line.lower():
                    results.append(
                        {
                            "file": str(file_path.relative_to(self.root)),
                            "line": lineno,
                            "snippet": line.strip()[:200],
                        }
                    )
                    if len(results) >= max_results:
                        break
        return results

    async def index(self, relative_path: str = ".", *, progress_cb: ProgressCallback | None = None) -> dict:
        """Walk every file under `relative_path`, hashing and sizing each one.

        Unlike every other method on this class, the work here is genuinely
        proportional to workspace size — hundreds of files take measurably
        longer than one — which is what makes `progress_cb` meaningful
        rather than decorative. `conduit.server.index_workspace` passes a
        callback that reports real MCP progress notifications; tests pass
        nothing, or a plain recorder, since this doesn't depend on MCP at all.
        """
        root = self._resolve(relative_path)
        files = [p for p in sorted(root.rglob("*")) if p.is_file()]
        total = len(files)

        entries: list[dict] = []
        by_hash: dict[str, list[str]] = {}
        for done, path in enumerate(files, start=1):
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            rel = str(path.relative_to(self.root))
            entries.append(
                {
                    "file": rel,
                    "size_bytes": len(data),
                    "sha256": digest,
                    "lines": data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0),
                }
            )
            by_hash.setdefault(digest, []).append(rel)
            if progress_cb is not None:
                await progress_cb(done, total)

        duplicate_groups = [group for group in by_hash.values() if len(group) > 1]
        return {
            "file_count": total,
            "total_bytes": sum(e["size_bytes"] for e in entries),
            "duplicate_groups": duplicate_groups,
            "files": entries,
        }
