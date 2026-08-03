# AsterMax Mechanical 0.6 beta

Portable Windows x64 finite-element learning and preliminary-calculation application with an original Mechanical-style workflow.

## Verified functional scope

### Tutorial 01 — restricted linear static solid

1. Import a STEP/STP file representing one rectangular prism, or create the 200 x 40 x 20 mm cantilever example.
2. Define isotropic linear-elastic material properties.
3. Select fixed and loaded faces.
4. Define a total force vector.
5. Generate a structured first-order TET4 mesh.
6. Assemble and solve the three-dimensional stiffness system.
7. Review displacement, von Mises stress, loaded-face displacement, reactions and equilibrium.
8. Export HTML, CSV and JSON calculation files.

### WS02.2–WS02.4 — scoping and Object Generator

- creates persistent Named Selections for XMin, XMax, YMin, YMax, ZMin and ZMax;
- reports face area, center and scoped mesh-node count;
- generates a fixed support or force scope from a selected Named Selection;
- updates the Outline tree and invalidates the previous solution when scoping changes.

### WS04.1 — mesh convergence

- solves the same static case with five progressively refined element sizes;
- compares maximum displacement and maximum von Mises stress against the finest generated mesh;
- reports node and element counts, equilibrium error and solve time;
- provides a convergence table, graph and HTML/CSV export.

### WS04.2 — Design Points

- performs a user-defined sweep of force magnitude while preserving force direction;
- solves each point with the same material, boundary conditions and mesh size;
- reports displacement, von Mises stress, simple safety factor and equilibrium;
- provides a response graph and HTML/CSV export.

### WS07.1 — modal cantilever

- solves a slender rectangular cantilever with Euler-Bernoulli beam finite elements;
- uses a consistent mass matrix and configurable density, element count and requested modes;
- reports up to six natural frequencies;
- compares each mode with the closed-form cantilever solution;
- exports a modal table and report.

### WS07.2 — steady-state thermal

- solves scalar heat conduction on the structured TET4 mesh;
- accepts conductivity, hot/cold faces and prescribed temperatures;
- reports temperature limits, total heat flow, heat flux and energy balance;
- compares opposite-face conduction with the one-dimensional analytical solution;
- exports a thermal table and report.

## Automated Windows verification

The current CI reference model is a 200 x 40 x 20 mm structural-steel cantilever.

- static mesh: 54 nodes and 96 TET4 elements;
- static maximum displacement: 0.097544606 mm;
- static maximum von Mises stress: 20.742688 MPa;
- modal first frequency: 407.69041 Hz;
- modal analytical difference: approximately 1.31e-5 percent;
- thermal heat flow: 14.4 W;
- thermal energy-balance error: approximately 2.84e-14.

CI also runs the mesh-convergence engine, publishes a self-contained single-file Windows executable and opens the GUI in an automated startup test.

## Recommended workflow for a preliminary memorandum

1. Import or create the supported prism.
2. Define material, support and load.
3. Solve the base static model.
4. Run Mesh Convergence and choose an acceptance criterion before interpreting stresses.
5. Run Design Points when load sensitivity is relevant.
6. Export the base calculation report and the verification-study reports.
7. Compare with an independent analytical model.
8. Have the assumptions and results reviewed by a competent engineer.

## Mandatory limitations

This remains a deliberately restricted beta.

- STEP import uses the axis-aligned Cartesian envelope of STEP points; it is not an OpenCASCADE BREP import.
- Only one rectangular/prismatic body is supported by the verified 3-D static and thermal paths.
- Named Selections are limited to the six prism faces.
- Design Points currently vary only force magnitude.
- Modal analysis is a one-dimensional Euler-Bernoulli beam model, not a general 3-D TET4 eigenanalysis.
- Thermal analysis supports prescribed temperatures and constant isotropic conductivity; no convection, radiation or thermal contact.
- No verified assemblies, contacts, joints, plasticity, large deformation, buckling, fatigue, transient dynamics or submodeling yet.
- The general Ribbon still contains roadmap and demonstration commands outside the verified tutorial tabs.

Reports are preliminary engineering aids and do not provide regulatory certification or professional sign-off.

## Build

```powershell
dotnet publish windows/AsterMax.MechanicalGui/AsterMax.MechanicalGui.csproj `
  -c Release `
  -r win-x64 `
  --self-contained true `
  -p:PublishSingleFile=true
```
