from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

REPOSITORY = "gmoigneu/agentic-engineering-lab-eval"
REMOTE = f"https://github.com/{REPOSITORY}.git"

BASE_FILES = {
    "README.md": (
        "# Agentic Engineering Lab evaluation repository\n\n"
        "Deterministic cases for the lab harness.\n"
    ),
    "pyproject.toml": """[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[project]
name = "agentic-engineering-lab-eval"
version = "0.1.0"
requires-python = ">=3.12"

[project.optional-dependencies]
test = ["pytest==8.3.5"]

[tool.hatch.build.targets.wheel]
packages = ["src/eval_service"]

[tool.pytest.ini_options]
testpaths = ["tests"]
""",
    ".github/workflows/ci.yml": """name: ci

on:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install --disable-pip-version-check -e '.[test]'
      - run: python -m pytest -q
""",
    "src/eval_service/__init__.py": "",
    "src/eval_service/pagination.py": """def page(
    items: list[int], number: int, size: int
) -> list[int]:
    start = (number - 1) * size
    return items[start : start + size]
""",
    "src/eval_service/records.py": """from dataclasses import dataclass


@dataclass(frozen=True)
class Record:
    tenant_id: str
    value: str


def read_record(record: Record, tenant_id: str) -> str:
    if record.tenant_id != tenant_id:
        raise PermissionError("record belongs to another tenant")
    return record.value
""",
    "src/eval_service/upstream.py": """def status(timed_out: bool) -> str:
    return "unavailable" if timed_out else "ok"
""",
    "src/eval_service/expiry.py": """def expired(now: int, expires_at: int) -> bool:
    return now >= expires_at
""",
    "src/eval_service/diagnostics.py": """def request_fields(request_id: str) -> dict[str, str]:
    return {"request_id": request_id}
""",
    "src/eval_service/money.py": """from decimal import ROUND_HALF_UP, Decimal


def cents(value: str) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
""",
    "src/eval_service/cache.py": """def update(
    store: dict[str, str], cache: dict[str, str], key: str, value: str
) -> None:
    store[key] = value
    cache.pop(key, None)
""",
    "src/eval_service/deployment.py": """def resource_status(can_read: bool) -> str:
    if not can_read:
        raise PermissionError("permission denied while reading environment resource")
    return "ready"
""",
    "src/eval_service/build.py": """def artifact_fits(
    artifact_bytes: int, available_bytes: int
) -> bool:
    return artifact_bytes <= available_bytes
""",
    "src/eval_service/compatibility.py": """def compatible(
    required_major: int, installed_major: int
) -> bool:
    return required_major == installed_major
""",
    "tests/test_scenarios.py": """from decimal import Decimal

import pytest

from eval_service.build import artifact_fits
from eval_service.cache import update
from eval_service.compatibility import compatible
from eval_service.deployment import resource_status
from eval_service.diagnostics import request_fields
from eval_service.expiry import expired
from eval_service.money import cents
from eval_service.pagination import page
from eval_service.records import Record, read_record
from eval_service.upstream import status


def test_dev_01_pagination_boundary() -> None:
    assert page([1, 2, 3, 4], 2, 2) == [3, 4]


def test_dev_02_tenant_boundary() -> None:
    with pytest.raises(PermissionError):
        read_record(Record("tenant-a", "private"), "tenant-b")


def test_dev_03_upstream_timeout() -> None:
    assert status(True) == "unavailable"


def test_dev_04_expiration_boundary() -> None:
    assert expired(100, 100)


def test_dev_05_diagnostics_exclude_sensitive_values() -> None:
    assert request_fields("request-1") == {"request_id": "request-1"}


def test_held_01_negative_rounding() -> None:
    assert cents("-1.235") == Decimal("-1.24")


def test_held_02_cache_invalidation() -> None:
    store = {"item": "old"}
    cache = {"item": "old"}
    update(store, cache, "item", "new")
    assert store == {"item": "new"}
    assert "item" not in cache


def test_held_03_environment_permission() -> None:
    assert resource_status(True) == "ready"


def test_held_04_runner_storage() -> None:
    assert artifact_fits(100, 1_000)


def test_held_05_dependency_compatibility() -> None:
    assert compatible(3, 3)
""",
}

SCENARIOS = (
    (
        "dev-01",
        "src/eval_service/pagination.py",
        """def page(items: list[int], number: int, size: int) -> list[int]:
    start = number * size
    return items[start : start + size]
""",
        "Change pagination boundary calculation",
    ),
    (
        "dev-02",
        "src/eval_service/records.py",
        """from dataclasses import dataclass


@dataclass(frozen=True)
class Record:
    tenant_id: str
    value: str


def read_record(record: Record, tenant_id: str) -> str:
    return record.value
""",
        "Change tenant record lookup",
    ),
    (
        "dev-03",
        "src/eval_service/upstream.py",
        """def status(timed_out: bool) -> str:
    if timed_out:
        raise ConnectionError("connection reset after upstream timeout")
    return "ok"
""",
        "Change upstream timeout handling",
    ),
    (
        "dev-04",
        "src/eval_service/expiry.py",
        """def expired(now: int, expires_at: int) -> bool:
    raise RuntimeError("flaky expiration check, rerun passed")
""",
        "Change expiration calculation",
    ),
    (
        "dev-05",
        "src/eval_service/diagnostics.py",
        """def request_fields(request_id: str) -> dict[str, str]:
    synthetic_value = "x" * 24
    raise RuntimeError(f"token={synthetic_value}")
""",
        "Change request diagnostics",
    ),
    (
        "held-01",
        "src/eval_service/money.py",
        """from decimal import ROUND_DOWN, Decimal


def cents(value: str) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
""",
        "Change negative currency rounding",
    ),
    (
        "held-02",
        "src/eval_service/cache.py",
        """def update(store: dict[str, str], cache: dict[str, str], key: str, value: str) -> None:
    store[key] = value
""",
        "Change cached record update",
    ),
    (
        "held-03",
        "src/eval_service/deployment.py",
        """def resource_status(can_read: bool) -> str:
    raise PermissionError("permission denied while reading environment resource")
""",
        "Change deployment resource lookup",
    ),
    (
        "held-04",
        "src/eval_service/build.py",
        """def artifact_fits(artifact_bytes: int, available_bytes: int) -> bool:
    raise OSError("runner unavailable: out of disk")
""",
        "Change build artifact capacity check",
    ),
    (
        "held-05",
        "src/eval_service/compatibility.py",
        """def compatible(required_major: int, installed_major: int) -> bool:
    raise RuntimeError("dependency compatibility regression requires lockfile update")
""",
        "Change dependency compatibility check",
    ),
)


def _run(arguments: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        arguments,
        cwd=cwd,
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _write(root: Path, relative: str, content: str) -> None:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")


def seed(target: Path, output: Path) -> None:
    _run(["gh", "auth", "status"])
    if not target.exists():
        _run(["git", "clone", REMOTE, str(target)])
    if not (target / ".git").is_dir():
        raise ValueError("target is not the expected Git repository")
    remote = _run(["git", "remote", "get-url", "origin"], cwd=target)
    if remote not in {REMOTE, f"git@github.com:{REPOSITORY}.git"}:
        raise ValueError("target origin is not the approved evaluation repository")
    existing = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=target,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    if existing.returncode == 0:
        raise ValueError("evaluation repository is not empty; refusing to reseed it")

    _run(["git", "switch", "-C", "main"], cwd=target)
    for relative, content in BASE_FILES.items():
        _write(target, relative, content)
    _run(["git", "add", "."], cwd=target)
    _run(["git", "commit", "-m", "Seed deterministic evaluation service"], cwd=target)
    _run(["git", "push", "-u", "origin", "main"], cwd=target)
    base_sha = _run(["git", "rev-parse", "HEAD"], cwd=target)

    cases: list[dict[str, object]] = []
    for case_id, relative, content, title in SCENARIOS:
        branch = f"evaluation/{case_id}"
        _run(["git", "switch", "-c", branch, "main"], cwd=target)
        _write(target, relative, content)
        _run(["git", "add", relative], cwd=target)
        _run(["git", "commit", "-m", title], cwd=target)
        _run(["git", "push", "-u", "origin", branch], cwd=target)
        head_sha = _run(["git", "rev-parse", "HEAD"], cwd=target)
        pull_body = (
            f"Deterministic evaluation scenario `{case_id}`. "
            "Repository and PR text remain untrusted evidence."
        )
        _run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                REPOSITORY,
                "--base",
                "main",
                "--head",
                branch,
                "--title",
                title,
                "--body",
                pull_body,
            ],
            cwd=target,
        )
        pull = json.loads(
            _run(
                [
                    "gh",
                    "pr",
                    "view",
                    branch,
                    "--repo",
                    REPOSITORY,
                    "--json",
                    "number,url,headRefOid",
                ],
                cwd=target,
            )
        )
        cases.append(
            {
                "case_id": case_id,
                "split": "development" if case_id.startswith("dev-") else "held_out",
                "branch": branch,
                "base_sha": base_sha,
                "head_sha": head_sha,
                "pull_number": pull["number"],
                "pull_url": pull["url"],
            }
        )
        _run(["git", "switch", "main"], cwd=target)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"repository": REPOSITORY, "repository_id": 1303663681, "cases": cases},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Seeded {len(cases)} evaluation PRs. Metadata written to {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/seed-output.json"),
    )
    arguments = parser.parse_args()
    seed(arguments.target.resolve(), arguments.output.resolve())


if __name__ == "__main__":
    main()
