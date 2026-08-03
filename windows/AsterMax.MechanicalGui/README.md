# AsterMax Mechanical 0.5 beta

Portable Windows x64 GUI implementing the first usable Mechanical-style static structural tutorial with an original interface and internal TET4 solver.

## First functional tutorial

The **Static Tutorial** tab opens by default and implements this restricted sequence:

1. Import a STEP/STP file representing one rectangular or prismatic solid, or use **Example STEP** to create a 200 x 40 x 20 mm cantilever file.
2. Define an isotropic elastic material: Young's modulus, Poisson ratio and reference yield strength.
3. Select the fixed face and loaded face.
4. Define the total force components.
5. Generate a structured first-order tetrahedral TET4 mesh.
6. Assemble and solve the three-dimensional linear elastic stiffness system.
7. Review maximum displacement, equivalent von Mises stress, loaded-face displacement, total reactions and force-equilibrium error.
8. Export a preliminary HTML calculation report together with CSV and JSON result files.

## Verified reference case

The Windows CI solves a 200 x 40 x 20 mm cantilever with structural steel, XMin fixed and a 1000 N force in negative Z on XMax.

Reference smoke-test result for the current default mesh:

- 54 nodes;
- 96 TET4 elements;
- maximum displacement: approximately 0.0975446 mm;
- maximum von Mises stress: approximately 20.7427 MPa;
- relative force-equilibrium error: approximately 8.14e-13.

The exact finite-element values depend on the selected mesh size.

## Interface corrections in 0.5

- taller Ribbon with icons above text instead of overlapping labels;
- functional Static Tutorial selected at startup;
- empty viewport before geometry import instead of a fictitious demonstration part;
- actual prism dimensions, mesh, supports, load vector, deformed-shape exaggeration and result legend;
- clearer Details category rows and wider units selector;
- light CAD theme by default, with optional dark theme.

## Mandatory limitations

This is a deliberately narrow beta. It accepts only one rectangular/prismatic solid represented by the axis-aligned envelope of the STEP points. It rejects or warns for curved surfaces, holes, fillets and assemblies.

It currently does **not** provide certified treatment of:

- arbitrary BREP topology;
- automatic face identity from OpenCASCADE;
- contact or multi-body assemblies;
- plasticity, large deflection, buckling, dynamics or fatigue;
- higher-order elements;
- regulatory or professional sign-off.

The generated report is a preliminary engineering aid. Results must be checked through mesh convergence, analytical comparison and review by a competent engineer before use in a formal calculation memorandum.

## Other GUI areas

The remaining Ribbon tabs preserve the broader Mechanical-style roadmap, including Geometry, Connections, Mesh, Environment, Results and Code_Aster integration. Some of those general commands are still demonstration or deck-preparation functions; the verified path in this build is the **Static Tutorial** tab.

## Build

```powershell
dotnet publish windows/AsterMax.MechanicalGui/AsterMax.MechanicalGui.csproj `
  -c Release `
  -r win-x64 `
  --self-contained true `
  -p:PublishSingleFile=true
```
