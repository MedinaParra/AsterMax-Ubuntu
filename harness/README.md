# AsterMax Coding Harness

The coding harness is the deterministic control layer used to build AsterMax with bounded coding agents.

The harness does **not** trust an agent's statement that code is correct. A change becomes a release candidate only when its WorkPackage scope is respected and every mandatory evidence gate passes.

## Development loop

```text
Specification -> H0 Supervisor -> H1 Architect -> H2 Implementation
                                -> H3 Test Engineer
                                -> H4 Numerical Validator (when physics/numerics change)
                                -> H5 Critic
                                -> deterministic gates
                                -> H6 Release Judge
                                -> human merge gate
```

## Core rules

1. Every coding task starts from a versioned `WorkPackageV1`.
2. The work package limits paths, file count, objectives and prohibited actions.
3. Unknown gates are rejected.
4. A numerical-impact package must include a numerical-validation gate.
5. PASS requires evidence from an executable/checkable gate. Prose approval is not evidence.
6. The implementation role cannot act as Release Judge.
7. FEA fields, solver outputs and benchmark results must never be fabricated to satisfy tests.
8. Human merge remains mandatory for the PMV.

## Local use

```powershell
python -m pip install -e ".[dev]"
astermax-harness validate harness/workpackages/W2_solver_bridge.yaml
astermax-harness run harness/workpackages/W2_solver_bridge.yaml --base-ref origin/main
```

`run` checks the Git diff against the package scope and then executes the configured deterministic gates.

## Evidence

The runner emits a JSON decision containing:

- WorkPackage identity and hash
- changed files
- each gate status
- command and exit code when applicable
- captured output tail
- final decision: `PASS`, `REWORK`, or `REJECT`

A PASS means the defined harness gates passed. It is not a claim that an engineering algorithm is physically valid beyond the benchmarks included in that WorkPackage.
