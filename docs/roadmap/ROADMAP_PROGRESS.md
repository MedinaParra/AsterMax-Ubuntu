# AsterMax Mechanical roadmap execution ledger

This ledger is the source-level gate for the M01–M08 implementation roadmap. A feature is counted only when its source/design acceptance evidence is present. Compilation and runtime validation remain mandatory after aggregate progress reaches 50%.

## Progress model

The roadmap is divided into 20 workshop-equivalent increments. Each certified increment is worth 5%.

| Increment | Scope | Source/design gate | Runtime gate | Status |
|---|---|---|---|---|
| 01 | WS01.1 Mechanical Basics | Accepted | Passed at 50% gate | Complete |
| 02 | WS02.1 2D Gear and Rack | Accepted | Passed at 50% gate | Complete |
| 03 | WS02.2 Named Selections | Accepted | Passed at 50% gate | Complete |
| 04 | WS02.3 Object Generator | Accepted | Passed at 50% gate | Complete |
| 05 | WS02.4 Object Generator with Named Selections | Accepted | Passed at 50% gate | Complete |
| 06 | WS03.1 Pump Assembly with Contact | Accepted | Passed at 50% gate | Complete |
| 07 | WS03.2 Beam Connections | Accepted | Passed at 50% gate | Complete |
| 08 | WS04.1 Mesh Convergence | Accepted | Passed at 50% gate | Complete |
| 09 | WS04.2 Design Points | Accepted | Passed at 50% gate | Complete |
| 10 | WS05.1 Mesh Creation | Accepted | Passed at 50% gate | Complete |
| 11 | WS05.2 Mesh Control | Accepted | Validation required | Source-complete |
| 12 | WS06.1 Contact Offset Control | Accepted | Domain regression passed; nonlinear benchmark required | Source-complete |
| 13 | WS06.2 Joints | Accepted | Domain regression passed; MPC/kinematic benchmark required | Source-complete |
| 14 | WS06.3 Remote Boundary Conditions | Accepted | Domain regression passed; MPC/equilibrium benchmark required | Source-complete |
| 15 | WS06.4 Constraint Equations | Accepted | Validation required | Source-complete |
| 16 | WS07.1 Modal Analysis | Pending | Required | Pending |
| 17 | WS07.2 Steady-State Thermal | Pending | Required | Pending |
| 18 | WS07.3 Multistep Analysis | Pending | Required | Pending |
| 19 | WS08.1 Eigenvalue Buckling | Pending | Required | Pending |
| 20 | WS08.2 Submodeling | Pending | Required | Pending |

**Current source/design progress: 75%.**

## Certified source evidence

### Increment 01 — WS01.1 Mechanical Basics

Mechanical-style layout, STEP/CAD-face scoping, material/support/load/mesh/solution objects, versioned project services, persistent general-CAD TET4 execution, displacement/stress/reaction recovery and explicit unsupported-flow failures are present.

### Increment 02 — WS02.1 2D Gear and Rack

`TwoDimensionalAnalysisDomain.cs` defines plane stress, plane strain and axisymmetric formulations, stable planar sections and bodies, edge-scoped gear/rack interaction and deterministic validation. Evidence: `docs/validation/ws02-1-2d-gear-rack-contract.md`.

### Increment 03 — WS02.2 Named Selections

`NamedSelectionDomain.cs` defines stable manual and worksheet selections, typed topology scope, explicit criteria semantics and stale-geometry rejection. Evidence: `docs/validation/ws02-2-named-selections-contract.md`.

### Increment 04 — WS02.3 Object Generator

`ObjectGeneratorDomain.cs` defines stable generators, columns, rows and generated-object contracts with typed values, deterministic identifiers and explicit duplicate or incomplete-field failures. Evidence: `docs/validation/ws02-3-object-generator-contract.md`.

### Increment 05 — WS02.4 Object Generator with Named Selections

`NamedSelectionObjectGeneratorDomain.cs` binds rows to current named selections and retains stable selection, entity-count and geometry-signature audit data. Evidence: `docs/validation/ws02-4-object-generator-named-selections-contract.md`.

### Increment 06 — WS03.1 Pump Assembly with Contact

`ContactDomain.cs` defines stable source/target face scopes, frictionless, frictional, bonded and no-separation behavior, detection settings and deterministic contact validation. Evidence: `docs/validation/ws03-1-pump-assembly-contact-contract.md`.

### Increment 07 — WS03.2 Beam Connections

`BeamConnectionDomain.cs` defines fixed, pinned, translational, rotational and generalized beam connections with six explicit degrees of freedom and current named-selection endpoints. Evidence: `docs/validation/ws03-2-beam-connections-contract.md`.

### Increment 08 — WS04.1 Mesh Convergence

`MeshConvergenceDomain.cs` defines monitored quantities, global/scoped/adaptive refinement, ordered mesh populations, finite results and consecutive relative-tolerance convergence. Evidence: `docs/validation/ws04-1-mesh-convergence-contract.md`.

### Increment 09 — WS04.2 Design Points

`DesignPointDomain.cs` defines stable input/output parameters, engineering units, ordered design points and study-to-analysis ownership. Validation rejects missing inputs, unknown parameters, duplicate IDs, names or sequences and non-finite values. Evidence: `docs/validation/ws04-2-design-points-contract.md`.

### Increment 10 — WS05.1 Mesh Creation

`MeshCreationDomain.cs` defines stable analysis-owned meshes, geometry-signature binding, global/minimum sizing, growth rate, body scopes, creation methods, element families and orders, compatibility checks and generated statistics. Evidence: `docs/validation/ws05-1-mesh-creation-contract.md`.

### Increment 11 — WS05.2 Mesh Control

`MeshControlDomain.cs` defines mesh-owned controls for body, face and edge sizing, sphere of influence, inflation and refinement with typed scopes, geometry revision binding, hard/soft behavior and deterministic validation. Evidence: `docs/validation/ws05-2-mesh-control-contract.md`.

### Increment 12 — WS06.1 Contact Offset Control

`ContactDomain.cs` defines explicit initial-gap treatment for preserve, signed user offset and adjust-to-touch behavior, with deterministic compatibility checks against pinball search radius and penetration tolerance. Windows Release build, the existing core solver regression and dedicated contact-offset domain fixtures passed before integration. Evidence: `docs/validation/ws06-1-contact-offset-control-contract.md`.

### Increment 13 — WS06.2 Joints

`JointDomain.cs` defines Fixed, Revolute, Cylindrical, Translational, Universal, Spherical and Planar joint families with deterministic local-frame mobility, elastic stiffness, travel/angle limits, stop stiffness and named-selection scoping. Windows Release build, core solver regression and seven-family joint domain fixtures passed before integration. Evidence: `docs/validation/ws06-2-joints-contract.md`.

### Increment 14 — WS06.3 Remote Boundary Conditions

`RemoteBoundaryConditionDomain.cs` defines remote displacement, force and moment conditions with global/local coordinate frames, rigid/deformable coupling, weighting semantics, remote points, component compatibility and named-selection scoping. Windows Release build, core solver regression and remote BC domain fixtures passed before integration. Evidence: `docs/validation/ws06-3-remote-boundary-conditions-contract.md`.

### Increment 15 — WS06.4 Constraint Equations

`ConstraintEquationDomain.cs` defines linear multi-point equations over mesh-node and remote-point DOFs with finite non-zero coefficients, duplicate-term rejection, finite RHS and explicit dimensional scaling for translation/rotation coupling. Evidence: `docs/validation/ws06-4-constraint-equations-contract.md`.

## Compile gate

The 50% gate passed on Windows x64: restore, Release build, tutorial capability smoke tests, self-contained single-file publish, bundled Gmsh verification and artifact upload completed successfully. Every subsequent increment must preserve this gate.

WS06.1 through WS06.3 preserved the Windows Release build and core solver smoke and passed shared domain regressions before integration. WS06.4 must preserve the same gate and pass its algebraic constraint fixtures before integration. Source-complete status does not imply that contact, joints, remote coupling or constraint equations are fully assembled/enforced by the solver; physical and solver-level MPC benchmarks remain mandatory.
