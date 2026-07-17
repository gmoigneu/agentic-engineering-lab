import pytest

from agentic_lab.gateway.patch_apply import apply_text_diff


def test_text_patch_applies_exact_context_and_supports_add_delete() -> None:
    diff = """--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,2 @@
-old
+new
 keep
--- /dev/null
+++ b/src/new.py
@@ -0,0 +1 @@
+created
--- a/src/remove.py
+++ /dev/null
@@ -1 +0,0 @@
-remove
"""

    result = apply_text_diff(
        diff,
        {"src/app.py": b"old\nkeep\n", "src/remove.py": b"remove\n"},
    )

    assert result[0].content == b"new\nkeep\n"
    assert result[1].content == b"created\n"
    assert result[2].content is None


def test_text_patch_rejects_context_that_does_not_match_the_pinned_base() -> None:
    diff = "--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-old\n+new\n"

    with pytest.raises(ValueError, match="context"):
        apply_text_diff(diff, {"src/app.py": b"different\n"})


def test_text_patch_accepts_removed_line_that_looks_like_a_header() -> None:
    diff = """--- a/readme.txt
+++ b/readme.txt
@@ -1 +1 @@
---- heading
++++ heading
"""

    applied = apply_text_diff(diff, {"readme.txt": b"--- heading\n"})

    assert applied[0].content == b"+++ heading\n"
