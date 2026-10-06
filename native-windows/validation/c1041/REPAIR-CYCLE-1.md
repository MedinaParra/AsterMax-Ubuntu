# C10.41 repair cycle 1

RC1: BLOCKED. Windows GUI, native Windows solver and save/reopen have not been demonstrated by this cycle.

Base: `2cca892cb1d733f01f55139f144dfc41d0e68aa1`, direct child of `add0efb6c15625c77b43c0a52abe7213aaadd1ba`.
Code tested: `d4c602b739f72638787eee01c50daf67f61bec68`.
Target: `agent/c1041-ws01-rc1-integration`; isolated local worktree: `agent/c1041-local-repair-20261006`.
AGENTS.md: NOT_FOUND in workspace scan and remote recursive tree.
No main edits, bulk merge or changes to the certified C10.40 physics/patch chain.

## Selective integration

| Capability from C10.29 | Decision | Reason |
|---|---|---|
| Qualification policy | SKIP | Already seeded by C10.41 |
| Python qualification gate | ADAPT | Missing in C10.40; two reproduced admission bugs corrected |
| Qualification fixtures | ADAPT | Mechanical checks retained; obsolete C10.29 patch-chain assertions excluded |
| GUI qualification/solve hook | DEFER | Requires Windows compilation and validation against C10.40 handoff |
| Scope membership fingerprint | PORT pending | Useful for stale-result rejection; not yet integrated or validated |
| WS01 generator/inventory | ADAPT pending | Requires equivalence audit and reaction provenance |
| WS01 comparator | ADAPT pending | Original hardcodes geometry/support equivalence as true; unsuitable for RC1 admission |
| Surface/body/multimaterial/load history exporters | DEFER | No bulk port; preserve C10.40 implementations and evidence |
| MED bridge | ADAPT pending | Component-first averaging and support-only reaction summation require audit |

## Reproduced and repaired

The donor gate admitted missing displacement/Von Mises fields and explicitly unverified reaction provenance. The adapted gate blocks these, malformed/non-finite vectors and invalid convergence maxima. Complete and independently assembled applied-resultant attestations are required for full qualification. Source labels no longer declare independently verified solver execution. Top-level status uses PASS/BLOCKED; engineering warnings remain distinct from certification. Benchmark comparison remains separate.

## Executed checks

Linux x86_64; Python subprocess fixture tests; exit code 0 for each command below.
These are synthetic fixture regressions, not genuine FEA or Windows certification.

| Check | State | Command / evidence |
|---|---|---|
| Qualification regression | PASS | `python native-windows/test-c1041-mechanical-qualification.py`; 27 cases; qualification-fixtures-linux.log |
| Inherited patch chain | PASS | `python native-windows/validate-patch-chain.py`; patch-chain-linux.log |
| Whitespace | PASS | `git diff --check` |
| Baseline ancestry | PASS | `git merge-base --is-ancestor add0efb6c15625c77b43c0a52abe7213aaadd1ba HEAD` |
| Windows/Linux fixture CI | PASS | Actions run 37463607504 at `4b9cb99b7e91b6ff8c6d555c31b847d12d3db68f`; both jobs completed successfully; qualification fixtures and patch-chain validation only |

## RC1 acceptance gates

| Gates | State | Evidence |
|---|---|---|
| A Windows Release build; B startup | BLOCKED | Local runner is Linux; no Windows build performed in this cycle |
| C STEP; D visibility/Fit; E material; F contacts; G mesh; H BC; I loads | NOT_RUN | C10.40 evidence is prior evidence and is not recertified here |
| J compiled exporter | NOT_RUN | Patch-chain validation is not a compiled exporter test |
| K native Windows Code_Aster; L solve | BLOCKED | No native Windows execution environment available locally |
| M displacement; N Von Mises; O equilibrium; P GUI results | NOT_RUN | Fixture tests cannot satisfy these gates |
| Q save; R close; S reopen; T recovered model; U result revision | NOT_RUN | Actual GUI/persistence round trip still required |
| V C10.40 regression | NOT_RUN | Inherited patch-chain validation is narrower than product regression |

RC1 readiness: 0/22 acceptance gates PASS in this cycle. No RC1 release or executable produced.

CI evidence: https://github.com/MedinaParra/AsterMax-Ubuntu/actions/runs/37463607504
Remote tested tree equals local evidence tree `3139c56c417bd3398c6afaee8b6d334c643800a3`. Remote commit identities differ from local commits because publication used the GitHub connector after CLI push lacked authentication. The same tested file content was published without modifying main.
