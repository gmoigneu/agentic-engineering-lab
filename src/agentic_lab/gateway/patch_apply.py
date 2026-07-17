from __future__ import annotations

import re
from dataclasses import dataclass

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class TextHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class TextFilePatch:
    old_path: str | None
    new_path: str | None
    hunks: tuple[TextHunk, ...]


@dataclass(frozen=True)
class AppliedFile:
    old_path: str | None
    new_path: str | None
    content: bytes | None


def parse_text_diff(diff: str) -> tuple[TextFilePatch, ...]:
    lines = diff.splitlines()
    files: list[TextFilePatch] = []
    index = 0
    while index < len(lines):
        if not lines[index].startswith("--- "):
            index += 1
            continue
        if index + 1 >= len(lines) or not lines[index + 1].startswith("+++ "):
            raise ValueError("unified diff is missing its new-file header")
        old_path = _header_path(lines[index][4:])
        new_path = _header_path(lines[index + 1][4:])
        index += 2
        hunks: list[TextHunk] = []
        while index < len(lines) and not lines[index].startswith("--- "):
            if lines[index].startswith("diff --git "):
                index += 1
                continue
            if not lines[index].startswith("@@ "):
                index += 1
                continue
            match = _HUNK.match(lines[index])
            if match is None:
                raise ValueError("unified diff has an invalid hunk header")
            index += 1
            body: list[str] = []
            old_count = int(match.group(2) or "1")
            new_count = int(match.group(4) or "1")
            old_seen = 0
            new_seen = 0
            while index < len(lines) and (old_seen < old_count or new_seen < new_count):
                line = lines[index]
                if line == r"\ No newline at end of file":
                    index += 1
                    continue
                if not line or line[0] not in {" ", "+", "-"}:
                    raise ValueError("unified diff hunk contains an invalid line")
                body.append(line)
                if line[0] in {" ", "-"}:
                    old_seen += 1
                if line[0] in {" ", "+"}:
                    new_seen += 1
                if old_seen > old_count or new_seen > new_count:
                    raise ValueError("unified diff hunk counts do not match its body")
                index += 1
            if old_seen != old_count or new_seen != new_count:
                raise ValueError("unified diff hunk counts do not match its body")
            hunks.append(
                TextHunk(
                    old_start=int(match.group(1)),
                    old_count=old_count,
                    new_start=int(match.group(3)),
                    new_count=new_count,
                    lines=tuple(body),
                )
            )
        if old_path is None and new_path is None:
            raise ValueError("unified diff cannot delete and create /dev/null")
        if not hunks and old_path == new_path:
            raise ValueError("unified diff file has no hunks")
        files.append(TextFilePatch(old_path, new_path, tuple(hunks)))
    if not files:
        raise ValueError("unified diff contains no text files")
    return tuple(files)


def apply_text_diff(diff: str, originals: dict[str, bytes]) -> tuple[AppliedFile, ...]:
    applied: list[AppliedFile] = []
    for file_patch in parse_text_diff(diff):
        if file_patch.old_path is None:
            original = ""
            original_newline = True
        else:
            raw = originals.get(file_patch.old_path)
            if raw is None:
                raise ValueError("unified diff base file is unavailable")
            if b"\x00" in raw:
                raise ValueError("unified diff cannot apply to binary content")
            try:
                original = raw.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError("unified diff base file is not UTF-8 text") from error
            original_newline = original.endswith("\n")
        source_lines = original.splitlines()
        result: list[str] = []
        cursor = 0
        for hunk in file_patch.hunks:
            target = max(hunk.old_start - 1, 0)
            if target < cursor or target > len(source_lines):
                raise ValueError("unified diff hunk range is invalid")
            result.extend(source_lines[cursor:target])
            cursor = target
            old_seen = 0
            new_seen = 0
            for line in hunk.lines:
                marker, content = line[0], line[1:]
                if marker in {" ", "-"}:
                    if cursor >= len(source_lines) or source_lines[cursor] != content:
                        raise ValueError("unified diff context does not match the base file")
                    cursor += 1
                    old_seen += 1
                if marker in {" ", "+"}:
                    result.append(content)
                    new_seen += 1
            if old_seen != hunk.old_count or new_seen != hunk.new_count:
                raise ValueError("unified diff hunk counts do not match its body")
        result.extend(source_lines[cursor:])
        if file_patch.new_path is None:
            content = None
        else:
            rendered = "\n".join(result)
            if original_newline or file_patch.old_path is None:
                rendered += "\n"
            content = rendered.encode()
        applied.append(AppliedFile(file_patch.old_path, file_patch.new_path, content))
    return tuple(applied)


def _header_path(raw: str) -> str | None:
    value = raw.split("\t", 1)[0].strip()
    if value == "/dev/null":
        return None
    if value.startswith(("a/", "b/")):
        value = value[2:]
    if not value or value.startswith("/") or ".." in value.split("/") or "\x00" in value:
        raise ValueError("unified diff path is unsafe")
    return value
