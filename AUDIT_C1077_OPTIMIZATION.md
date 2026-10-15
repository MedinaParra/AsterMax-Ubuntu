# AsterMax C10.77 optimization audit — 2026-10-15

Audited head: ecffb6dfd934a99871c0322c61b2b30632f9490b. Main is not modified.

## Confirmed findings

1. HIGH — C10.77 rebuilds only the 81-entry base patch chain (ending C10.41), but its contract requires C10.42. Run 38787391853 passed all 81 patch applications, then failed cad_depth_guard, top_level_transaction, deferred_update, large_assembly_edges, render_scheduled, queued_paint and center_without_redraw. MSBuild was skipped. Fix: apply existing C10.42 candidate before contract and build, retaining all checks.
2. HIGH — C10.75 and C10.76 also rebuild only that baseline. Successful compilation does not establish that later candidate optimizations are integrated. Version labels are not cumulative source provenance.
3. MEDIUM — C10.75/76/77 scan source text. They do not instrument runtime Render/Update or measure import latency. C10.76 weights are heuristic; occurrence counts include declarations/comments and cannot establish a bottleneck or speedup.
4. MEDIUM — C10.77 checks comments and token presence, not control flow. PASS would establish only a static prerequisite, not one render per transaction.
5. MEDIUM — C10.42 disables displayed edges at 80 parts, but absence of displayed edges does not prove edge geometry is not built. Evaluate C10.48 lazy-edge candidate separately with memory and toggle regression checks.
6. MEDIUM — C10.42 queues worker-thread render requests before the UI coalescing check. A burst can still enqueue many callbacks. Measure queue count before changing cross-thread scheduling; preserve WinForms handle/disposal semantics.

## Changes in this audit

Workflow applies the existing C10.42 candidate after baseline reconstruction, before unchanged C10.77 and C10.52 guards and Windows x64 build. New audit branch is enabled for push validation. No solver, model, mesh or result semantics changed.

## Required runtime evidence

On identical machine/configuration, compare baseline and candidate using 1, 25, 80 and 200-part fixtures, three cold imports each. Capture split/import/first-frame durations, peak working set, actual render and actor creation counts, and Fit latency. Verify edge toggling, repeated import, cancelled import, close during pending render, save/reopen, meshing and native Code_Aster results. Keep the incident OT-1717 STEP test BLOCKED until the fixture is available. No numeric performance improvement is claimed.

## Status at audit submission

- PASS: repository/workflow inspection and prior 81/81 patch evidence.
- FAIL: original C10.77 static contract, with exact run evidence above.
- NOT_RUN: corrected Windows build, GUI regressions and runtime benchmark until new CI results exist.
- BLOCKED: exact incident STEP fixture absent.
