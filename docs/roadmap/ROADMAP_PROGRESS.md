# AsterMax Mechanical roadmap execution ledger

This ledger is the source-level gate for the M01–M08 implementation roadmap. A feature is counted only when its source/design acceptance evidence is present. Compilation and runtime validation remain intentionally deferred until aggregate progress reaches 50%.

## Progress model

The roadmap is divided into 20 workshop-equivalent increments. Each certified increment is worth 5%.

| Increment | Scope | Source/design gate | Runtime gate | Status |
|---|---|---|---|---|
| 01 | WS01.1 Mechanical Basics | Accepted | Deferred until 50% | Source-complete |
| 02 | WS02.1 2D Gear and Rack | Accepted | Deferred until 50% | Source-complete |
| 03 | WS02.2 Named Selections | Pending | Deferred until 50% | Pending |
| 04 | WS02.3 Object Generator | Pending | Deferred until 50% | Pending |
| 05 | WS02.4 Object Generator with Named Selections | Pending | Deferred until 50% | Pending |
| 06 | WS03.1 Pump Assembly with Contact | Pending | Deferred until 50% | Pending |
| 07 | WS03.2 Beam Connections | Pending | Deferred until 50% | Pending |
| 08 | WS04.1 Mesh Convergence | Pending | Deferred until 50% | Pending |
| 09 | WS04.2 Design Points | Pending | Deferred until 50% | Pending |
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

**Current source/design progress: 10%.**

## Increment 01 — WS01.1 Mechanical Basics

Accepted source evidence includes the Mechanical-style layout, STEP/CAD-face scoping, material/support/load/mesh/solution objects, versioned project services, a persistent general-CAD TET4 path, authentic displacement/stress/reaction recovery and explicit unsupported-flow failures. Runtime acceptance remains queued for the 50% compile gate.

## Increment 02 — WS02.1 2D Gear and Rack

Accepted source evidence:

- `TwoDimensionalAnalysisDomain.cs` defines plane stress, plane strain and axisymmetric formulations.
- Planar sections retain stable IDs, thickness, origin and analysis-plane orientation.
- Planar bodies retain geometry, section, material, role and persistent face signature.
- Gear/rack interaction is represented by stable source/target edge-selection IDs.
- Validation rejects invalid thickness, normals, identifiers, unknown sections, mixed formulations, missing active bodies and absent edge scope.
- `docs/validation/ws02-1-2d-gear-rack-contract.md` records the workflow and deferred runtime acceptance.

## Compile gate

Before 50%, verification is limited to source, schema, state-machine and workflow consistency. At exactly 50%, the branch must be compiled and the first ten increments exercised with recorded results before any of them can be promoted from `Source-complete` to `Validated`.
