# AsterMax Mechanical 0.7.1 beta

Portable Windows x64 finite-element application with a Mechanical-style workflow, real STEP visualization through Gmsh/OpenCASCADE, selectable CAD faces and verified tutorial capabilities.

## Starting the portable package

Extract the complete ZIP before running the program. Keep this structure together:

```text
AsterMax-Mechanical-0.7.1-beta.exe
RUN-AsterMax.cmd
tools/gmsh/gmsh.exe
```

Run `RUN-AsterMax.cmd` from the extracted root directory. The `tools/gmsh` directory is required for STEP files containing holes, cylinders, fillets, curved faces or other non-prismatic topology.

## Standard workflow

Use the normal **Workflow**, **Home**, **Geometry**, **Mesh** and **Environment** commands. No additional tutorial is required.

1. Import a STEP/STP solid.
2. Assign the material.
3. Generate the mesh.
4. Use a normal left click to select a face. The complete OpenCASCADE face is highlighted in amber.
5. Press **Fixed Support**. The scoped face is stored and shown in teal.
6. Select another face and press **Force**. The scoped face is stored and shown in red.
7. Select either object in the Outline to review the face identifier, surface area, triangle count and node count in Details.

Rotate with **Ctrl + left drag** or the middle mouse button. Use the mouse wheel to zoom.

## Real STEP visualization and meshing

### Rectangular prism

A single rectangular prism uses the verified internal route:

- real dimensions read from STEP;
- selectable prism faces;
- structured linear TET4 mesh;
- fixed support and force scoping;
- internal three-dimensional linear-elastic solution;
- displacement, von Mises stress, reactions and equilibrium;
- preliminary calculation report export.

### General single-solid STEP

A STEP containing curved surfaces, holes or non-prismatic topology uses Gmsh/OpenCASCADE:

- native STEP topology import;
- closed exterior skin display, without drawing internal tetrahedral faces;
- unstructured linear TET4 volume mesh;
- persistent CAD-face identifiers;
- selection of planar or curved faces;
- real support/load scopes containing the corresponding boundary triangles and mesh nodes;
- visual markers for selected, supported and loaded faces.

The arbitrary unstructured TET4 static solve is not enabled yet. AsterMax validates the general CAD preprocessing state and blocks **Solve** instead of returning simulated stresses. The next required block is the sparse Code_Aster/general TET4 solve adapter.

## Existing tutorial capability verification

No new tutorials were added for this correction. Before packaging, Windows CI verifies the capabilities already represented by the existing tutorials:

- linear static TET4 solution, displacement, von Mises stress, reactions and equilibrium;
- Named Selections and object scoping on prism faces;
- mesh convergence study;
- force Design Points;
- Euler-Bernoulli modal beam calculation and analytical comparison;
- steady-state TET4 heat conduction and energy balance.

Reference checks include:

- static model: 54 nodes, 96 TET4, maximum displacement 0.097544606 mm and maximum von Mises stress 20.742688 MPa;
- modal first frequency: 407.69041 Hz with approximately 1.31e-5 percent analytical difference;
- thermal heat flow: 14.4 W with approximately 2.84e-14 energy-balance error.

## Standard workflow verification

The package is also tested independently of the tutorial buttons:

- a complex STEP with two cylindrical through-holes is generated;
- surface preview and TET4 volume mesh must be non-empty;
- OpenCASCADE faces must remain independently selectable;
- every selectable face must contain boundary triangles and mesh nodes;
- two distinct faces are assigned as support and load scopes;
- the normal prism workflow is solved and must satisfy the equilibrium gate;
- the Windows GUI must start without a fatal error.

The included `AsterMax_Complex_STEP_Smoke.step` can be used to reproduce the complex-CAD preprocessing route locally.

## Current limitations

- General CAD currently supports one closed STEP/STP solid; assemblies and multiple bodies are not yet mapped.
- General CAD face selection and support/load scoping work, but its static solution still awaits the sparse Code_Aster/general TET4 adapter.
- IGES and BREP are not presented as functional formats in this build.
- The verified internal static and thermal solution paths remain limited to a rectangular prism.
- Modal analysis is a one-dimensional Euler-Bernoulli model, not a general 3-D eigensolver.
- Thermal analysis does not yet include convection, radiation or thermal contact.
- Contacts, joints, plasticity, large deformation, buckling, fatigue, transient dynamics and submodeling are not yet verified.

Reports are preliminary engineering aids and do not provide regulatory certification or professional sign-off.
