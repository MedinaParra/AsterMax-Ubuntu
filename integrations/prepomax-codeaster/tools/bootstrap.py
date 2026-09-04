#!/usr/bin/env python3
"""Clone the reviewed PrePoMax upstream revision and apply the Code_Aster overlay.

The bootstrap is intentionally fail-closed and pins an exact upstream commit. Network
transport failures are retried, but a different upstream revision is never accepted.
"""
from __future__ import print_function
import argparse, shutil, subprocess, sys, time
from pathlib import Path

UPSTREAM = "https://github.com/tsvilans/PrePoMax.git"
UPSTREAM_SHA = "3669e65581650e5d9d868aa761db9efd856f8571"
HERE = Path(__file__).resolve().parent

def run(args, cwd=None):
    print("+", " ".join(str(x) for x in args))
    subprocess.check_call([str(x) for x in args], cwd=str(cwd) if cwd else None)

def remove_destination(destination):
    if destination.exists(): shutil.rmtree(str(destination), ignore_errors=True)

def clone_pinned_upstream(upstream, destination, attempts=3):
    last_error = None
    for attempt in range(1, attempts + 1):
        remove_destination(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            run(["git","-c","http.version=HTTP/1.1","clone","--filter=blob:none","--no-checkout",upstream,destination])
            run(["git","fetch","--depth","1","origin",UPSTREAM_SHA], cwd=destination)
            run(["git","checkout","--detach",UPSTREAM_SHA], cwd=destination)
            actual = subprocess.check_output(["git","rev-parse","HEAD"], cwd=str(destination), text=True).strip()
            if actual.lower() != UPSTREAM_SHA.lower(): raise RuntimeError("Pinned upstream mismatch: expected %s, got %s" % (UPSTREAM_SHA, actual))
            run(["git","submodule","sync","--recursive"], cwd=destination)
            run(["git","-c","http.version=HTTP/1.1","submodule","update","--init","--recursive","--depth","1"], cwd=destination)
            print("Pinned upstream bootstrap PASS on attempt", attempt)
            return
        except (subprocess.CalledProcessError, RuntimeError) as exc:
            last_error = exc
            print("Pinned upstream bootstrap attempt %d/%d failed: %s" % (attempt, attempts, exc))
            remove_destination(destination)
            if attempt < attempts: time.sleep(2 * attempt)
    raise RuntimeError("Unable to bootstrap exact pinned upstream %s after %d attempts: %s" % (UPSTREAM_SHA, attempts, last_error))

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--destination", required=True); parser.add_argument("--upstream", default=UPSTREAM); args = parser.parse_args()
    destination = Path(args.destination).resolve()
    if destination.exists() and any(destination.iterdir()): raise SystemExit("Destination must not exist or must be empty: " + str(destination))
    clone_pinned_upstream(args.upstream, destination)
    for script in [
        "apply_overlay.py","apply_model_translation.py","apply_results_bridge.py","apply_harness_runtime.py",
        "apply_harness_runtime_fixups.py","apply_harness_ui.py","apply_solver_settings_ui.py","apply_import_probe.py",
        "apply_results_demo.py","apply_astermax_ai.py","apply_branding.py","apply_workdir_fix.py"]:
        run([sys.executable, HERE / script, destination])
    print(); print("Prepared:", destination); print("Upstream revision:", UPSTREAM_SHA); print("Product: AsterMax Mechanical + AsterMax AI"); print("Next: open PrePoMax.sln and build the solution.")
    return 0

if __name__ == "__main__": raise SystemExit(main())
