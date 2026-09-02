#!/usr/bin/env python3
"""Clone the reviewed PrePoMax upstream revision and apply the Code_Aster overlay."""

from __future__ import print_function

import argparse
import subprocess
import sys
from pathlib import Path

UPSTREAM = "https://github.com/tsvilans/PrePoMax.git"
UPSTREAM_SHA = "3669e65581650e5d9d868aa761db9efd856f8571"
HERE = Path(__file__).resolve().parent


def run(args, cwd=None):
    print("+", " ".join(str(x) for x in args))
    subprocess.check_call([str(x) for x in args], cwd=str(cwd) if cwd else None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", required=True)
    parser.add_argument("--upstream", default=UPSTREAM)
    args = parser.parse_args()

    destination = Path(args.destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit("Destination must not exist or must be empty: " + str(destination))

    destination.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", "--recursive", args.upstream, destination])
    run(["git", "checkout", UPSTREAM_SHA], cwd=destination)
    run(["git", "submodule", "update", "--init", "--recursive"], cwd=destination)
    run([sys.executable, HERE / "apply_overlay.py", destination])
    run([sys.executable, HERE / "apply_model_translation.py", destination])

    print()
    print("Prepared:", destination)
    print("Upstream revision:", UPSTREAM_SHA)
    print("Next: open PrePoMax.sln and build the solution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
