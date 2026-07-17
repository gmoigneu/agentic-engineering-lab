from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from pydantic import BaseModel

MAX_READ_LINES = 200
MAX_READ_BYTES = 32_000
MAX_SEARCH_RESULTS = 50
MAX_MATCH_BYTES = 1_000


class SourceLocator(BaseModel):
    locator: str
    pinned_sha: str
    content_hash: str
    untrusted: bool = True


class TreeEntry(BaseModel):
    path: str
    object_type: str


class FileReadResult(BaseModel):
    text: str
    locator: SourceLocator
    truncated: bool = False


class TextMatch(BaseModel):
    path: str
    line: int
    text: str
    locator: SourceLocator
    truncated: bool = False


class StructureMatch(BaseModel):
    path: str
    line: int
    symbol: str
    kind: str
    locator: SourceLocator


class HistoryEntry(BaseModel):
    commit_sha: str
    subject: str
    paths: list[str]
    locator: str
    untrusted: bool = True


@dataclass(frozen=True)
class RepositorySnapshot:
    """An immutable, credential-free source snapshot supplied by the gateway."""

    pinned_sha: str
    files: dict[str, str]
    history: tuple[HistoryEntry, ...] = ()

    def __post_init__(self) -> None:
        if len(self.pinned_sha) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in self.pinned_sha
        ):
            raise ValueError("snapshot requires an immutable lowercase SHA")
        for path in self.files:
            self._safe_path(path)

    def list_tree(self, prefix: str = "", depth: int = 8) -> list[TreeEntry]:
        if not 0 <= depth <= 32:
            raise ValueError("tree depth must be between 0 and 32")
        if prefix:
            self._safe_path(prefix)
        root = PurePosixPath(prefix) if prefix else None
        entries: list[TreeEntry] = []
        for path in sorted(self.files):
            candidate = PurePosixPath(path)
            if root and root not in candidate.parents and candidate != root:
                continue
            relative_depth = len(candidate.parts) - (len(root.parts) if root else 0)
            if relative_depth <= depth:
                entries.append(TreeEntry(path=path, object_type="file"))
        return entries

    def read_file(self, path: str, start_line: int = 1, end_line: int = 200) -> FileReadResult:
        self._safe_path(path)
        if (
            start_line < 1
            or end_line < start_line
            or end_line - start_line >= MAX_READ_LINES
        ):
            raise ValueError("invalid or oversized line window")
        if path not in self.files:
            raise FileNotFoundError(path)
        lines = self.files[path].splitlines()
        selected = lines[start_line - 1 : end_line]
        full_text = "\n".join(selected)
        text = _truncate_utf8(full_text, MAX_READ_BYTES)
        actual_end = min(end_line, len(lines), start_line + text.count("\n"))
        return FileReadResult(
            text=text,
            truncated=len(lines) > end_line or text != full_text,
            locator=self._locator(path, start_line, actual_end, text),
        )

    def search_text(
        self, query: str, path_prefix: str = "", regex: bool = False, limit: int = 30
    ) -> list[TextMatch]:
        if not query or len(query) > 1_000:
            raise ValueError("search query must contain 1 to 1000 characters")
        if not 1 <= limit <= MAX_SEARCH_RESULTS:
            raise ValueError(f"search limit must be between 1 and {MAX_SEARCH_RESULTS}")
        if path_prefix:
            self._safe_path(path_prefix)
        try:
            matcher = re.compile(query) if regex else None
        except re.error as error:
            raise ValueError("invalid regular expression") from error
        matches: list[TextMatch] = []
        for path, content in self.files.items():
            if not path.startswith(path_prefix):
                continue
            for number, line in enumerate(content.splitlines(), start=1):
                if (matcher and matcher.search(line)) or (not matcher and query in line):
                    matches.append(
                        TextMatch(
                            path=path,
                            line=number,
                            text=_truncate_utf8(line, MAX_MATCH_BYTES),
                            locator=self._locator(path, number, number),
                            truncated=len(line.encode()) > MAX_MATCH_BYTES,
                        )
                    )
                    if len(matches) == limit:
                        return matches
        return matches

    def search_structure(
        self, symbol: str, language: str = "python", path_prefix: str = "", limit: int = 30
    ) -> list[StructureMatch]:
        """Search parsed structure without exposing ast-grep or shell command text."""
        if language != "python":
            raise ValueError("only the configured Python structure adapter is available")
        if not symbol or len(symbol) > 255 or not symbol.isidentifier():
            raise ValueError("symbol must be a Python identifier")
        matches: list[StructureMatch] = []
        for path, content in sorted(self.files.items()):
            if not path.endswith(".py") or not path.startswith(path_prefix):
                continue
            try:
                tree = ast.parse(content, filename=path)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and (
                    node.name == symbol
                ):
                    matches.append(
                        StructureMatch(
                            path=path,
                            line=node.lineno,
                            symbol=node.name,
                            kind="class" if isinstance(node, ast.ClassDef) else "function",
                            locator=self._locator(
                                path, node.lineno, getattr(node, "end_lineno", node.lineno)
                            ),
                        )
                    )
                    if len(matches) == limit:
                        return matches
        return matches

    def git_history(self, path_prefix: str = "", limit: int = 20) -> list[HistoryEntry]:
        if not 1 <= limit <= 100:
            raise ValueError("history limit must be between 1 and 100")
        if path_prefix:
            self._safe_path(path_prefix)
        return [
            entry
            for entry in self.history
            if not path_prefix or any(path.startswith(path_prefix) for path in entry.paths)
        ][:limit]

    def _locator(
        self, path: str, start: int, end: int, excerpt: str | None = None
    ) -> SourceLocator:
        if excerpt is None:
            lines = self.files[path].splitlines()
            excerpt = _truncate_utf8("\n".join(lines[start - 1 : end]), MAX_READ_BYTES)
        content_hash = hashlib.sha256(excerpt.encode()).hexdigest()
        return SourceLocator(
            locator=f"{path}#L{start}-L{end}", pinned_sha=self.pinned_sha, content_hash=content_hash
        )

    @staticmethod
    def _safe_path(path: str) -> None:
        candidate = PurePosixPath(path)
        if candidate.is_absolute() or ".." in candidate.parts or "\x00" in path:
            raise ValueError("snapshot path must be repository-relative")


def _truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode()
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode(errors="ignore")
