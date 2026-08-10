# AsterMax Windows 2.0 beta — Tutorial Certification Matrix

This ledger is intentionally strict. `Passed` means the exact workshop has reproducible Windows E2E evidence: faithful inputs, editable objects, authentic numerical formulation, numerical/graphical results, JSON/CSV/HTML evidence, save/reopen persistence, automated Windows regression, independent/reference comparison with an explicit tolerance, controlled invalid-input failure, and clean operation termination.

Strict certification is `Passed / 20 * 100`.

## Baseline for this branch

- Windows build: **Passed on the base branch at iteration start; must be re-verified after each change**.
- GUI startup: **Passed on the base branch at iteration start; must be re-verified after each change**.
- Bundled Gmsh package: **Passed on the base branch at iteration start; must be re-verified after each release build**.
- Tutorial curriculum certification at branch creation: **0/20 = 0%**.
- The historical `--solver-smoke` is a rectangular-prism/core-engine smoke and is **not** tutorial certification.
- `Unavailable`, `Skipped`, `NotRun` and `NotCertified` never count as `Passed`.

| ID | Workshop | Required physical capability | Status | Evidence |
|---|---|---|---|---|
| WS01.1 | Mechanical Basics | Import `Cap_fillets.stp`; aluminium; 1.1 MPa external pressure; frictionless supports; mesh; stress, deformation and safety factor; yield verification. | NotCertified | — |
| WS02.1 | 2D Gear and Rack | 12 mm plane-stress model; gear/rack contact; 2500 N; remote displacement; recover moment reaction. | NotCertified | — |
| WS02.2 | Named Selections | Manual and geometric-criteria selections; fixed support; radial displacement; persistent scoping. | NotCertified | — |
| WS02.3 | Object Generator | Two plates with 12 holes; initial beam connection; generate all 12; fixed lower edges; 1000 N; solve. | NotCertified | — |
| WS02.4 | Object Generator with Named Selections | Import valve; criteria-based selections; generate objects on selections; solve real model. | NotCertified | — |
| WS03.1 | Linear Structural Analysis | Five-part pump assembly; per-body materials; contacts; frictionless support; 100 N bearing load; deflection <= 0.075 mm and yield verification. | NotCertified | — |
| WS03.2 | Beam Connections | Flange assembly; fasteners as beam connections; fixed end; remote 1000 N force at Z=100 mm; reactions and stresses. | NotCertified | — |
| WS04.1 | Mesh Evaluation | Import arm; tension/bending loads; multiple real meshes; quality and convergence at web region. | NotCertified | — |
| WS04.2 | Parameter Management | Import `Bracket.stp`; bracket/gusset thickness parameters; design combinations; compare structural responses. | NotCertified | — |
| WS05.1 | Mesh Creation | Mesh workshop assembly; symmetry; per-body methods; controls and real statistics. | NotCertified | — |
| WS05.2 | Mesh Control | Import `assembly_solid.stp`; controls that correct geometric defects; quantify mesh effect. | NotCertified | — |
| WS06.1 | Contact Offset Control | Valve/piston with 0.39 mm gap; solve untreated and with initial offset; compare contact/results. | NotCertified | — |
| WS06.2 | Joints | Four-part assembly; retain required contact; create automatic joints; edit DOFs; solve. | NotCertified | — |
| WS06.3 | Remote Boundary Conditions | Jack base; point mass; remote force; correct remote locations/coupling; solve and recover reactions. | NotCertified | — |
| WS06.4 | Constraint Equations | Hook fastener; impose and verify `5*UY - UX = 0`; 25 mm X associated with 5 mm Y. | NotCertified | — |
| WS07.1 | Modal Analysis | Import `Machine_Frame.stp`; 3D modal; eight-hole versus four-corner-hole mounting; authentic mode shapes. | NotCertified | — |
| WS07.2 | Steady-State Thermal | Import `Pump_housing.stp`; plastic vs aluminium; 60 C mount, 90 C interior, exterior convection to 20 C; temperature and heat flow. | NotCertified | — |
| WS07.3 | Multistep Analysis | Pipe clamp in four steps; bolt pretension then lock; internal pressure at step 3; axial force at step 4; result history. | NotCertified | — |
| WS08.1 | Eigenvalue Buckling | Fixed-free pipe; 10,000 lbf compression; eigenvalue buckling; compare critical load to ~65,648.3 lbf; safety factor and yield check. | NotCertified | — |
| WS08.2 | Submodeling | Coarse global pump housing; transfer cut-boundary displacements; fine submodel; interpolation and local convergence verification. | NotCertified | — |

## Current strict result

- Passed: **0**
- Failed: **0**
- Unavailable: **0**
- NotRun / NotCertified: **20**
- Strict curriculum certification: **0/20 = 0%**

## Separate progress dimensions

These dimensions must never be substituted for the strict curriculum percentage:

1. interface coverage;
2. domain implementation;
3. numerical execution;
4. physical verification;
5. curriculum certification (`Passed/20`);
6. industrial readiness.

A workshop row changes to `Passed` only in the same change set that adds its exact fixture, Windows E2E execution, exported evidence, persistence check and reference/tolerance comparison.
