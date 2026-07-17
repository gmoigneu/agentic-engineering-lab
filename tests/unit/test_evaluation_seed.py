import os
import subprocess
import sys
from pathlib import Path
from runpy import run_path

_SEED = run_path("scripts/seed_evaluation_repository.py", run_name="seed_module")
BASE_FILES = _SEED["BASE_FILES"]
SCENARIOS = _SEED["SCENARIOS"]
_write = _SEED["_write"]


def _materialize(root: Path) -> None:
    for relative, content in BASE_FILES.items():
        _write(root, relative, content)


def test_seed_base_passes_and_every_scenario_has_one_failing_check(tmp_path: Path) -> None:
    _materialize(tmp_path)
    environment = {**os.environ, "PYTHONPATH": str(tmp_path / "src")}
    baseline = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        check=False,
    )
    assert baseline.returncode == 0

    for case_id, relative, content, _title in SCENARIOS:
        _write(tmp_path, relative, content)
        failed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", f"-k={case_id.replace('-', '_')}"],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            check=False,
        )
        assert failed.returncode == 1, case_id
        _write(tmp_path, relative, BASE_FILES[relative])
