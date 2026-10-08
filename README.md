# AsterMax Mechanical C10.41 RC1

**Open-source CAE / FEA workflow for Windows x64 with native Code_Aster integration.**

AsterMax Mechanical is an engineering pre/post-processing environment derived from the PrePoMax ecosystem and oriented toward a Mechanical-style workflow: geometry, materials, contacts, loads, meshing, solving and result review from a single desktop interface.

> **Current status:** C10.41 RC1 — engineering-validated candidate on Windows x64.

## RC1 status

| Item | Status |
|---|---|
| Windows x64 Release build | PASS |
| Native Windows Code_Aster installation/execution | PASS |
| Compiled AsterMax exporter | PASS |
| Real contact deck solve | PASS |
| STEP/contact/gravity regression | PASS |
| Native GUI workflow conformance | PASS |
| Save / close / reopen solved project | PASS |
| Mandatory qualification gate | PASS |

**Validated baseline commit:** `9b823e943ffafa3b94de428ff5375feb625939e6`

**Qualification workflow:** GitHub Actions run `37651647328` — completed successfully on 2026-10-07.

This RC1 is a release candidate, not a claim of universal FEA certification. Every engineering model remains subject to appropriate verification, benchmark comparison, mesh/convergence review, material-model validation and applicable design codes.

## What the RC1 workflow proves

The C10.41 qualification pipeline exercised the current Windows workflow end to end:

```text
CAD / STEP
  ↓
AsterMax GUI
  ↓
Mechanical model tree
  ↓
Materials + contacts + loads
  ↓
Mesh / model export
  ↓
Native Windows Code_Aster
  ↓
Solve
  ↓
Results
  ↓
Save project
  ↓
Close application
  ↓
Reopen solved PMX in a separate GUI process
```

The qualification also preserves regression coverage for real STEP geometry, contact, gravity, stress/result identity and project portability.

## Current RC1 artifacts

The validated workflow generated the following GitHub Actions artifacts:

- `AsterMax-C10.41-Windows-x64-Test-Distribution`
- `AsterMax-C10.41-Workflow-Conformance`
- `AsterMax-C10.41-Mechanical-Tree-Evidence`

The Windows x64 test distribution is tied to the validated RC1 baseline above. A formal GitHub Release/tag is still pending; until then, the qualification run is the traceable source for the RC1 artifact.

## Main engineering direction

AsterMax is being developed as a practical mechanical-engineering environment with emphasis on:

- STEP-based mechanical assemblies;
- a Mechanical-style analysis tree;
- structural static workflows;
- automatic/default material assignment where appropriate;
- contact-oriented modelling;
- gravity and mechanical loading;
- native Code_Aster solving on Windows;
- displacement, stress and reaction result review;
- project persistence and reproducibility;
- validation evidence instead of silent success;
- explicit PASS / FAIL / BLOCKED / NOT_RUN qualification logic.

## Development policy after RC1

`main` contains the validated C10.41 RC1 baseline plus documentation updates.

RC1 should remain functionally frozen. New functionality and behavior changes belong in a new RC2 development branch and must pass the same end-to-end qualification philosophy before promotion.

## Repository note

The repository name `AsterMax-Ubuntu` is historical. The current C10.41 RC1 qualification described here is focused on the **native Windows x64** path with **Code_Aster for Windows**.

Legacy Linux/Ubuntu work remains part of the project history, but it must not be confused with the current Windows RC1 qualification baseline.

## Independence and licensing

AsterMax does not redistribute proprietary Ansys source code, icons, screenshots or documentation. Mechanical-style terminology is used only to describe workflow intent and user-experience direction.

Upstream components retain their respective licenses. Project-specific source in this repository must be used consistently with those licenses and notices.

## Qualification boundary

A successful automated workflow means that the tested software chain completed the declared qualification contract for the tested model and environment. It does **not** mean that every element formulation, contact condition, nonlinear model, material law, geometry or engineering use case has been independently validated.

For production engineering decisions, always preserve model inputs, solver version, mesh information, boundary conditions, result files and verification evidence.

---

**AsterMax Mechanical C10.41 RC1**  
Windows x64 · Native Code_Aster · End-to-end qualification PASS
