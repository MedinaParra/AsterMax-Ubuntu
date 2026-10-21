# C12.03 — Native Windows runner static-contract findings

Date: 2026-10-21. Scope: **audit only**. No Windows binaries, GUI, solver runtime, STEP/VTK/ActiViz transformations, workflow or `main` are changed by this document.

## Fixed-reference inspection

- Baseline audit branch: `agent/c1201-native-distribution-audit` at `e9febabab55b812ad6610f04863683809ca0a8a2`.
- Baseline audit blob SHA: `6da22e488824f49fa94e32fcb5499ef990dfa94c`.
- Native Code_Aster CMD runner blob: `fe0e203d16cd19b20f84b54eb16bf50fd4711bca`.
- Native Code_Aster PowerShell runner blob: `77e84f1152182f4d07a80349ba9827243dcf4451`.
- Historical Windows build run: `39613742204`, Release x64 MSBuild PASS, post-build branded EXE lookup FAIL.

## Newly identified C12.02 patch limitation

The unpublished C12.02 proposal requires `function Invoke-WindowsBackend {`, while the **real** Code_Aster PowerShell runner declares `function Invoke-WindowsBackend([string]$Backend, [string]$ExportPath, [string]$Directory, [int]$TimeoutMs) {`. This valid parameterized declaration would be incorrectly rejected. Static regression fixtures must represent the actual runner syntax, not just simplified `function Name {` fixtures.

A further C12.02 edge case: a nonempty runner containing **only comments** could incorrectly pass when comment filtering leaves no text and therefore skips its conditional checks. Such a file must explicitly fail the static contract.

The local C12.03 correction accepts both function declaration forms, strips complete comment-only lines from static checks, and explicitly rejects runners without noncomment statements. It is a heuristic. It cannot prove successful GUI launch, Windows Code_Aster availability, solver execution or benchmark performance.

## Validation boundaries

Local isolated source fixture was checked against the exact C12.01 Git blob, then corrected and tested against 15 independent synthetic/static cases; all 15 passed, as did Python syntax checking. The CMD invocation and parameterized PowerShell signatures were compared against the repository's native Windows launchers. **This document does not claim a Windows run**.

The corrected checker remains **unpublished** because the authorized GitHub update of the existing audit file was blocked by connection safety checks. Do not route around that restriction. The `.github/workflows/astermax-c1198-windows-x64-build-gate.yml` still uses obsolete `PrePoMax.exe` lookup; it requires a separately authorized correction and a new Windows run before distribution regression status changes.

| Area | Status |
| --- | --- |
| Historical C11.99 Windows x64 MSBuild | PASS |
| C12.03 Windows compilation | NOT_RUN |
| GUI and Code_Aster native execution | NOT_RUN |
| STEP/VTK static-chain historical checks | PASS |
| C12.03 local static regression fixtures | PASS (15/15) |
| Dynamic STEP/VTK/ActiViz benchmark | NOT_RUN |
| Distribution gate regression | BLOCKED (workflow unchanged) |

Never infer FPS, timings, memory reductions or solver results from these static checks.
