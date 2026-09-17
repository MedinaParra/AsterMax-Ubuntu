# C10.18: integrated Mechanical workflow

## Intended behavior

The project Outline owns Solution Information and the five supported Code_Aster
result fields. Selecting a field displays it in the main graphics area, with
scrollable result details below the Outline. Selecting a model object returns
to the model view. The results view is reused while switching fields or views.

The reference is the user-supplied `Mechanical_Introduction_17.0_v1(2).zip`:
M01 Introduction (interface and procedure), WS01.1 Mechanical Basics (Solve and
result selection), and M04 Postprocessing (display and result controls).
This implements that interaction pattern; it is not full ANSYS feature parity.

## Repairs

- Field and deformation-scale changes now render immediately.
- Contours, Deformed, Edges and camera commands route to the active result view.
- Results Explorer and FEA Viewport open the embedded workspace.
- Native scalar-bar colors remain authoritative; the duplicate legend is hidden.
- Detached details have scrolling so short windows do not hide probe controls.
- A changed model fails the fingerprint check before results can be displayed.
- New/open project reset disposes result ownership and clears the previous solve.
- Current Solution nodes no longer retain the incomplete-state hint.
- The older C10.14 patch preserves C10.17 exact output validation in the runner.

## Verification scope

The Windows workflow builds the pinned upstream source plus the complete patch
chain, installs native Code_Aster, validates a real tetrahedral model and then
runs the GUI audit on a real hexahedral solve. The GUI audit invokes Solve,
selects all five fields, toggles Contours/Deformed/Edges, invokes camera commands,
captures the workspace and VTK framebuffer, switches views, checks Solution
Information, rejects stale results and checks disposal.

Camera checks verify successful invocation, not exact camera matrices. The
separate button inventory verifies delegates, icons and accessibility names;
it does not execute every editing command. A passing inventory must not be
described as a complete end-to-end test of all buttons.

The workflow uploads `UI_AUDIT.json`, inventory reports, native solver evidence,
and captures. A portable package is uploaded only after all required steps pass.
Consult the run for the exact commit being downloaded; compilation alone is
insufficient to claim solver or GUI validation.

## Remaining limitations

- Solving uses the existing synchronous transaction; cancellation is not added.
- Result fields are the five fields supported by the existing MED bundle.
- Code_Aster is an external installation, not included in the portable package.
- Broad CAD editing, meshing and every material/load dialog need additional
  interactive coverage; the new regression focuses on the integrated workflow.
