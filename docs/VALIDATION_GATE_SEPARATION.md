# Validation Gate Separation

AsterMax treats deterministic software correctness and numerical/physics evidence as separate mandatory gates.

## Windows PMV Core

Owns deterministic software evidence:

- contract validation;
- state-machine invariants;
- scope and provenance logic;
- solver bridge fail-closed behavior;
- artifact hashing and identity checks;
- unit/regression tests that do not require an external FEA installation.

It runs on Windows and explicitly excludes `tests/benchmarks/**` from its pytest invocation. On pull requests it also compares the candidate against the PR base and fails if any numerical benchmark is deleted. A baseline that predates the numerical suite is therefore not falsely rejected, while a candidate cannot make the core gate green by removing an existing numerical test.

## Code_Aster Numerical Validation

Owns external numerical evidence:

- pinned Code_Aster image/build identity;
- `run_aster` / `run_ctest` availability;
- pinned reference testcase discovery;
- reference testcase execution and TEST_RESU/reference assertions;
- retained numerical logs and environment evidence.

The numerical benchmark remains fail-closed. Missing Code_Aster is a numerical-gate failure, not a deterministic Windows-core failure.

## Why this is stricter, not weaker

Running every test in every environment creates false negatives and obscures which invariant failed. Separating the gates makes failure attribution explicit while preserving both requirements:

1. deterministic software gates must pass; and
2. numerical validation gates must pass.

Neither gate can substitute for the other, and W2 feature code is forbidden from modifying the infrastructure that decides numerical acceptance.
