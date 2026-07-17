import re
from pathlib import Path

_LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")


def test_local_documentation_links_resolve() -> None:
    root = Path(__file__).parents[2]
    documents = [root / "README.md", *sorted((root / "docs").glob("*.md"))]
    broken: list[str] = []
    for document in documents:
        for target in _LINK.findall(document.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            path_text = target.split("#", 1)[0]
            if path_text and not (document.parent / path_text).resolve().exists():
                broken.append(f"{document.relative_to(root)} -> {target}")
    assert not broken, "broken local documentation links\n" + "\n".join(broken)
