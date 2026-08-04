# AsterMax roadmap execution control

## Progress model

Overall progress is measured against 100 weighted points, not the number of visible commands.

| Block | Weight |
|---|---:|
| 0.8.1 reproducible numerical base | 8 |
| M01 project workflow | 8 |
| M02 preprocessing | 12 |
| M03 structural analysis | 14 |
| M04 postprocessing and parameters | 10 |
| M05 mesh controls | 10 |
| M06 connections | 14 |
| M07 modal, thermal and multistep | 12 |
| M08 buckling and submodeling | 8 |
| 2.0 certification | 4 |

## Current state

- Overall progress: **12%**.
- Current block: **0.8.1 reproducible numerical base**.
- Compilation gate: disabled until overall progress reaches 50%.
- Work before 50% is limited to source architecture, schemas, fixtures, acceptance criteria and deterministic implementation design.

## Iteration protocol

1. Select the next incomplete acceptance item.
2. Implement or specify it without adding empty UI commands.
3. Verify consistency through source inspection and deterministic fixtures.
4. Update the progress ledger.
5. Continue immediately with the next item.
6. At 50%, enable compilation and numerical validation.

## 0.8.1 acceptance ledger

- [x] CSR storage is represented in the solver source.
- [x] PCG tolerance and iteration bounds are explicit.
- [x] Solver output includes residual and equilibrium metrics.
- [x] Surface force distribution is area weighted.
- [x] TET4 degeneracy checks are explicit.
- [ ] Remove build-time source rewriting from production CI.
- [ ] Freeze a versioned solver configuration object.
- [ ] Define axial, bending, patch and reaction benchmarks as data fixtures.
- [ ] Define deterministic result comparison tolerances.
- [ ] Define project migration policy for solver settings.

## 50% build gate

Compilation is permitted only after the ledger reaches 50 weighted points. At that point the pipeline must run:

- source build;
- startup test;
- all available analytical benchmarks;
- STEP import and mesh test;
- result persistence test;
- tutorial workflow tests available at that milestone.
