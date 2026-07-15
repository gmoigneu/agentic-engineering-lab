from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from pydantic import BaseModel


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


@dataclass(frozen=True)
class RepositorySnapshot:
    """An immutable, credential-free source snapshot supplied by the gateway."""

    pinned_sha: str
    files: dict[str, str]

    def list_tree(self, prefix: str = "", depth: int = 8) -> list[TreeEntry]:
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

    def read_file(self, path: str, start_line: int = 1, end_line: int = 500) -> FileReadResult:
        if path not in self.files:
            raise FileNotFoundError(path)
        lines = self.files[path].splitlines()
        selected = lines[start_line - 1 : end_line]
        text = "\n".join(selected)
        return FileReadResult(
            text=text,
            truncated=len(lines) > end_line,
            locator=self._locator(path, start_line, min(end_line, len(lines))),
        )

    def search_text(
        self, query: str, path_prefix: str = "", regex: bool = False
    ) -> list[TextMatch]:
        matcher = re.compile(query) if regex else None
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
                            text=line,
                            locator=self._locator(path, number, number),
                        )
                    )
        return matches

    def _locator(self, path: str, start: int, end: int) -> SourceLocator:
        content_hash = hashlib.sha256(self.files[path].encode()).hexdigest()
        return SourceLocator(
            locator=f"{path}#L{start}-L{end}", pinned_sha=self.pinned_sha, content_hash=content_hash
        )
