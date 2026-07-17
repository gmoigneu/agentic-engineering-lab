from __future__ import annotations

import sys

from agentic_lab.executor.transport import RecipeExecutionRequest


def adapter_argv(request: RecipeExecutionRequest) -> tuple[str, ...]:
    if request.adapter == "noop_v1":
        if request.arguments:
            raise ValueError("noop_v1 does not accept arguments")
        return (sys.executable, "-m", "agentic_lab.executor.noop")
    if request.adapter in {"pytest_v1", "pytest_after_patch_v1"}:
        expected = (
            {"selector", "unified_diff"}
            if request.adapter == "pytest_after_patch_v1"
            else {"selector"}
        )
        if set(request.arguments) != expected:
            raise ValueError(f"{request.adapter} received invalid arguments")
        selector = request.arguments["selector"]
        if not isinstance(selector, str) or not selector or len(selector) > 500:
            raise ValueError("pytest_v1 selector is invalid")
        if any(character in selector for character in ";|&`$\n"):
            raise ValueError("pytest_v1 selector contains unsafe characters")
        return (sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", selector)
    if request.adapter == "ruff_check_v1":
        if request.arguments:
            raise ValueError("ruff_check_v1 does not accept arguments")
        return (sys.executable, "-m", "ruff", "check", "--no-cache", ".")
    raise ValueError("unknown recipe adapter")
