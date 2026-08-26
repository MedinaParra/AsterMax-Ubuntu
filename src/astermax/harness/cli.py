from __future__ import annotations

import argparse
import sys
from pathlib import Path

from astermax.harness.models import HarnessDecision
from astermax.harness.policy import validate_workpackage
from astermax.harness.runner import decision_json, load_workpackage, load_yaml, run_harness


def _repo_root() -> Path:
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "harness").exists():
            return candidate
    raise RuntimeError("Could not locate AsterMax repository root")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="astermax-harness")
    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate", help="Validate a WorkPackage contract")
    validate_parser.add_argument("workpackage")

    run_parser = sub.add_parser("run", help="Run deterministic gates for a WorkPackage")
    run_parser.add_argument("workpackage")
    run_parser.add_argument("--base-ref", default="origin/main")
    run_parser.add_argument("--repo-root", default=None)
    run_parser.add_argument("--output", default=None)

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if getattr(args, "repo_root", None) else _repo_root()

    if args.command == "validate":
        package, package_hash = load_workpackage(args.workpackage)
        config = load_yaml(repo_root / "harness" / "config" / "harness.v1.yaml")
        errors = validate_workpackage(package, set(config.get("gates", {})))
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 2
        print(f"VALID {package.workpackage_id} sha256={package_hash}")
        return 0

    decision = run_harness(args.workpackage, repo_root, args.base_ref)
    rendered = decision_json(decision)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    return 0 if decision.decision == HarnessDecision.PASS else 1


if __name__ == "__main__":
    sys.exit(main())
