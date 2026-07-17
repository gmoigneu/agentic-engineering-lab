from pathlib import Path
from runpy import run_path

import pytest

from agentic_lab.domain.enums import PolicyOutcome
from agentic_lab.policy.patch import PatchPolicy, validate_unified_diff

_RENDERER = run_path("scripts/render_evaluation_manifest.py", run_name="render_module")
render = _RENDERER["render"]


def test_rendered_evaluation_manifest_is_pinned_and_budgeted(tmp_path: Path) -> None:
    image = "ghcr.io/gmoigneu/agentic-lab-eval-executor@sha256:" + "a" * 64

    manifest = render(image, tmp_path / "manifest.json")

    assert manifest.repository_id == 1303663681
    assert manifest.budgets.max_usd == 0.2
    assert {recipe.image for recipe in manifest.recipes.values()} == {image}
    assert manifest.recipes["validate_patch"].adapter == "pytest_after_patch_v1"
    decision = validate_unified_diff(
        "--- a/src/eval_service/pagination.py\n"
        "+++ b/src/eval_service/pagination.py\n"
        "@@ -1 +1 @@\n-old\n+new\n",
        PatchPolicy(
            tuple(manifest.allowed_source_paths),
            tuple(manifest.protected_paths),
        ),
    )
    assert decision.outcome is PolicyOutcome.ALLOW

    with pytest.raises(ValueError, match="immutable digest"):
        render("mutable:latest", tmp_path / "invalid.json")
