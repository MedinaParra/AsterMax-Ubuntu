# AsterMax Mechanical C9.53 — Native Fork Baseline

This iteration establishes AsterMax as a real native fork of PrePoMax source code for Windows.

## Architectural contract

- One native executable: `AsterMax Mechanical.exe`.
- No runtime shell, embedding, `SetParent`, or secondary PrePoMax process.
- Internal inherited namespaces may remain `PrePoMax` temporarily to preserve compatibility.
- Existing `FrmMain`, `Controller`, `ModelTree`, `vtkControl`, CAD import, selection and meshing command infrastructure are preserved.
- The user-facing UI is transformed in source and compiled into the native executable.

## Visible increment

A new AsterMax visual layer is injected into `FrmMain` with:

- AsterMax product header.
- Mechanical-style contextual tabs: Home, Geometry, Model, Connections, Mesh, Environment, Solution, Results, View.
- Native buttons wired to existing handlers for New, Open, Import Geometry, Save, Fit, Isometric, geometry analysis, mesh generation and result display.
- Light engineering workspace styling.
- Visible `mm · N · MPa` PMV unit contract.
- ModelTree terminology adjusted toward Geometry / Supports / Solution without changing model semantics.

## Truth boundary

GitHub Actions compiles the source on a real Windows runner. Static build gates are authoritative for compilation and artifact identity.

The headless CI runner does not prove interactive STEP rendering, mouse rotation or face selection. These remain `RUNTIME WINDOWS` gates and must not be claimed as passed until tested interactively.

No FEA solve is executed in C9.53. Code_Aster integration is the next architectural gate after the native GUI and STEP viewport runtime are validated.
