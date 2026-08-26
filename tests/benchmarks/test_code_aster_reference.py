from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


def test_code_aster_reference_case_is_numerically_validated(tmp_path: Path) -> None:
    """Fail-closed external numerical gate using Code_Aster's own TEST_RESU testcases."""

    run_ctest = os.environ.get("ASTERMAX_RUN_CTEST") or shutil.which("run_ctest")
    reference_test = os.environ.get("ASTERMAX_CODE_ASTER_REFERENCE_TEST")

    if not run_ctest:
        pytest.fail(
            "Code_Aster numerical gate unavailable: configure ASTERMAX_RUN_CTEST or install run_ctest."
        )
    if not reference_test:
        pytest.fail(
            "Code_Aster numerical gate has no pinned reference testcase: set ASTERMAX_CODE_ASTER_REFERENCE_TEST."
        )

    result_dir = tmp_path / "resutest"
    selector = rf"(^|_){re.escape(reference_test)}$"
    command = [
        run_ctest,
        f"--resutest={result_dir}",
        "-j",
        "1",
        "-R",
        selector,
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    combined = completed.stdout + "\n" + completed.stderr
    if "No tests were found" in combined:
        pytest.fail(f"Pinned Code_Aster testcase was not found: {reference_test}")
    assert completed.returncode == 0, (
        f"Code_Aster reference testcase {reference_test!r} failed numerical validation.\n"
        f"stdout:\n{completed.stdout[-6000:]}\n"
        f"stderr:\n{completed.stderr[-6000:]}"
    )
