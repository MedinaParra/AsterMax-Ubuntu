# AsterMax Mechanical roadmap execution ledger

This ledger is the source-level gate for the M01–M08 implementation roadmap. A feature is counted only when its source/design acceptance evidence is present. Compilation and runtime validation remain intentionally deferred until aggregate progress reaches 50%.

## Progress model

The roadmap is divided into 20 workshop-equivalent increments. Each certified increment is worth 5%.

| Increment | Scope | Source/design gate | Runtime gate | Status |
|---|---|---|---|---|
| 01 | WS01.1 Mechanical Basics | Accepted | Deferred until 50% | Source-complete |
| 02 | WS02.1 2D Gear and Rack | Accepted | Deferred until 50% | Source-complete |
| 03 | WS02.2 Named Selections | Accepted | Deferred until 50% | Source-complete |
| 04 | WS02.3 Object Generator | Accepted | Deferred until 50% | Source-complete |
| 05 | WS02.4 Object Generator with Named Selections | Accepted | Deferred until 50% | Source-complete |
| 06 | WS03.1 Pump Assembly with Contact | Accepted | Deferred until 50% | Source-complete |
| 07 | WS03.2 Beam Connections | Accepted | Deferred until 50% | Source-complete |
| 08 | WS04.1 Mesh Convergence | Accepted | Deferred until 50% | Source-complete |
| 09 | WS04.2 Design Points | Accepted | Deferred until 50% | Source-complete |
| 10 | WS05.1 Mesh Creation | Pending | Required at 50% | Pending |
| 11 | WS05.2 Mesh Control | Pending | Required | Pending |
| 12 | WS06.1 Contact Offset Control | Pending | Required | Pending |
| 13 | WS06.2 Joints | Pending | Required | Pending |
| 14 | WS06.3 Remote Boundary Conditions | Pending | Required | Pending |
| 15 | WS06.4 Constraint Equations | Pending | Required | Pending |
| 16 | WS07.1 Modal Analysis | Pending | Required | Pending |
| 17 | WS07.2 Steady-State Thermal | Pending | Required | Pending |
| 18 | WS07.3 Multistep Analysis | Pending | Required | Pending |
| 19 | WS08.1 Eigenvalue Buckling | Pending | Required | Pending |
| 20 | WS08.2 Submodeling | Pending | Required | Pending |

**Current source/design progress: 45%.**

## Certified source evidence

### Increment 01 — WS01.1 Mechanical Basics

Mechanical-style layout, STEP/CAD-face scoping, material/support/load/mesh/solution objects, versioned project services, persistent general-CAD TET4 execution, displacement/stress/reaction recovery and explicit unsupported-flow failures are present. Runtime acceptance remains queued for the 50% compile gate.

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

## Compile gate

Before 50%, verification is limited to source, schema, state-machine and workflow consistency. At exactly 50%, the branch must be compiled and the first ten increments exercised with recorded results before any of them can be promoted from `Source-complete` to `Validated`.
