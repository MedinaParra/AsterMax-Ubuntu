# AsterMax Mechanical 0.7 beta

Portable Windows x64 finite-element application with an original Mechanical-style workflow, real STEP visualization through Gmsh/OpenCASCADE and verified tutorial solvers.

## Starting the portable package

Extract the complete ZIP before running the program. Keep this structure together:

```text
AsterMax-Mechanical-0.7.0-beta.exe
RUN-AsterMax.cmd
tools/gmsh/gmsh.exe
```

Run `RUN-AsterMax.cmd` or the executable from the extracted root directory. The `tools/gmsh` directory is required for STEP files containing holes, cylinders, fillets, curved faces or other non-prismatic topology.

## Real STEP import and meshing

Use **Home / Geometry → Import Geometry** or **Static Tutorial → Import STEP**.

### Rectangular prism

A single rectangular prism uses the verified internal route:

1. Real dimensions are read from the STEP file.
2. The prism is displayed in the viewport.
3. Material, fixed face, loaded face and force are defined.
4. A structured first-order TET4 mesh is generated.
5. The internal three-dimensional linear-elastic solver runs.
6. Results and a preliminary calculation report can be exported.

### General single-solid STEP

A STEP containing curved surfaces, holes or non-prismatic topology uses the Gmsh/OpenCASCADE route:

1. Gmsh imports the STEP topology through OpenCASCADE.
2. A real triangular surface preview is generated and displayed.
3. **Generate Mesh** asks for a target element size.
4. Gmsh creates an unstructured linear tetrahedral volume mesh.
5. AsterMax displays node, boundary-triangle and TET4 counts.

The general single-solid route currently stops after real volume meshing. Arbitrary-face selection, persistent CAD face identifiers and assembly into the general static solver are the next implementation block. The program deliberately blocks **Solve** for this route instead of returning fictitious stresses.

## Verified functional tutorial scope

### Tutorial 01 — restricted linear static solid

- isotropic linear elasticity and small displacement;
- fixed and loaded prism faces;
- total force vector;
- structured TET4 mesh;
- displacement, von Mises stress, reactions and equilibrium;
- HTML, CSV and JSON calculation files.

### WS02.2–WS02.4 — scoping and Object Generator

- persistent Named Selections for XMin, XMax, YMin, YMax, ZMin and ZMax;
- face area, center and mesh-node count;
- generated fixed support or force scope;
- Outline integration and solution invalidation after changes.

### WS04.1 — mesh convergence

- five progressively refined element sizes;
- displacement and von Mises comparison against the finest mesh;
- node count, TET4 count, equilibrium and solve time;
- table, graph and HTML/CSV export.

### WS04.2 — Design Points

- configurable force-magnitude sweep;
- real solution at each point;
- displacement, von Mises stress, simple safety factor and equilibrium;
- response graph and HTML/CSV export.

### WS07.1 — modal cantilever

- Euler-Bernoulli beam finite elements;
- consistent mass matrix;
- configurable density, elements and modes;
- analytical cantilever comparison.

### WS07.2 — steady-state thermal

- scalar heat conduction on structured TET4;
- constant isotropic conductivity;
- prescribed hot and cold faces;
- heat flow, heat flux and energy balance;
- one-dimensional analytical comparison.

## Automated Windows verification

CI executes all of the following before publishing:

- static reference model: 54 nodes, 96 TET4, maximum displacement 0.097544606 mm and maximum von Mises stress 20.742688 MPa;
- modal first frequency: 407.69041 Hz with approximately 1.31e-5 percent analytical difference;
- thermal heat flow: 14.4 W with approximately 2.84e-14 energy-balance error;
- complex OpenCASCADE STEP containing two cylindrical through-holes;
- real surface preview generation;
- real unstructured volume TET4 generation;
- self-contained Windows publication;
- automated GUI startup.

The included `AsterMax_Complex_STEP_Smoke.step` can be used to test the same complex-CAD route locally.

## Current limitations

- General CAD currently supports one closed STEP/STP solid; assemblies and multiple bodies are not yet mapped.
- General CAD can be visualized and tetrahedralized, but arbitrary CAD-face scoping and static solution are not yet enabled.
- IGES and BREP are not presented as functional formats in this build.
- The verified static and thermal solution paths remain limited to a rectangular prism.
- Prism Named Selections are limited to its six faces.
- Modal analysis is a one-dimensional Euler-Bernoulli model, not a general 3-D eigensolver.
- Thermal analysis does not yet include convection, radiation or thermal contact.
- No verified contacts, joints, plasticity, large deformation, buckling, fatigue, transient dynamics or submodeling.

Reports are preliminary engineering aids and do not provide regulatory certification or professional sign-off.
