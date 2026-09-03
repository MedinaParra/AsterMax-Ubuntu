#!/usr/bin/env python3
"""Contract tests for AsterMax harness safety boundaries. No FEA solver is invoked."""

import tempfile
from pathlib import Path

import astermax_harness as harness


def expect_harness_error(action, label):
    try:
        action()
    except harness.HarnessError:
        return
    raise AssertionError(label)


def main():
    with tempfile.TemporaryDirectory(prefix="astermax-harness-contract-") as temp:
        root = Path(temp)
        inside = harness.case_path(root, "results/Job-1.rmed")
        assert root.resolve() in inside.parents

        expect_harness_error(
            lambda: harness.case_path(root, "../outside.rmed"),
            "Harness allowed an artifact path to escape the case workspace.",
        )
        expect_harness_error(
            lambda: harness.case_path(root, str((root.parent / "absolute.rmed").resolve())),
            "Harness allowed an absolute solver-owned artifact path.",
        )

    print("AsterMax harness workspace contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
