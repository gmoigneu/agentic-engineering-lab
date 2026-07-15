import pytest

from agentic_lab.gateway.github_read import Archive, PinnedArchiveReader


def test_reader_refuses_mutable_or_missing_archive():
    reader = PinnedArchiveReader({(1, "a" * 40): Archive(1, "a" * 40, {"src/a.py": "x"})})
    assert reader.fetch_snapshot(1, "a" * 40).read_file("src/a.py").text == "x"
    with pytest.raises(FileNotFoundError):
        reader.fetch_snapshot(1, "main")
