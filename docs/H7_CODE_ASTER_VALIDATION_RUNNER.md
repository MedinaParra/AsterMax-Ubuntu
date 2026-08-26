# H7 — Code_Aster Numerical Validation Runner

## Purpose

This runner is an independent judge for W2 numerical validation. It deliberately lives outside `work/W2-solver-bridge`, so feature code cannot change the environment or testcase that decides whether its numerical gate passes.

## Reviewed environment

- Container: `simvia/code_aster:18.1.0`
- Reviewed Docker Hub digest prefix: `sha256:4629a21a1093`
- Pinned testcase: `ssls120c`
- Required tooling: `run_aster` and `run_ctest`

The workflow records the full runtime RepoDigest. A tag whose digest no longer starts with the reviewed prefix fails closed and requires a new infrastructure review.

## Why `ssls120c`

The Code_Aster source testcase includes a `MECA_STATIQUE` path and `TEST_RESU` checks against `REFERENCE='ANALYTIQUE'` for displacement and stress quantities. It is therefore suitable as an initial external reference check for the linear-static solver path. Passing this testcase validates the selected Code_Aster installation against its own analytical reference assertions; it does not by itself validate the hub-sprocket model.

## Fail-closed conditions

The CI job fails when:

1. the image cannot be pulled;
2. the runtime digest differs from the reviewed image prefix;
3. `run_aster` is unavailable;
4. `run_ctest` is unavailable;
5. the exact pinned testcase is not discovered;
6. the Code_Aster testcase exits non-zero;
7. expected evidence logs cannot be retained.

No condition is converted into SKIP/PASS.

## Evidence ownership

The job retains:

- the runtime image RepoDigest;
- tooling probe output;
- reference testcase output.

W2 remains responsible for proving its own bridge/worker/result-import path. H7 proves only that the external Code_Aster validation environment is pinned and numerically healthy enough to serve as an independent judge.
