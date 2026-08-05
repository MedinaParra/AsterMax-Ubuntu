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

**Current source/design progress: 40%.**

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

## Increment 03 — WS02.2 Named Selections

Accepted source evidence:

- `NamedSelectionDomain.cs` defines stable manual and worksheet-generated named selections.
- Entity typing prevents mixed vertex, edge, face, body and mesh-node scopes.
- Worksheet criteria include explicit comparison and Boolean semantics with finite-value validation.
- Evaluations retain resolved scope, geometry signature and timestamp.
- Resolution rejects stale geometry signatures and empty evaluated scopes instead of silently reusing obsolete topology IDs.
- `docs/validation/ws02-2-named-selections-contract.md` records downstream scoping and deferred runtime acceptance.

## Increment 04 — WS02.3 Object Generator

Accepted source evidence:

- `ObjectGeneratorDomain.cs` defines stable generator, column, row and generated-object contracts.
- Mandatory name and scope columns prevent anonymous or unscoped generated objects.
- Typed text, number, Boolean and identifier values are validated deterministically.
- Duplicate columns, duplicate rows, unknown values and incomplete required fields fail explicitly.
- Generated object IDs are reproducible from the generator and source row IDs.
- `docs/validation/ws02-3-object-generator-contract.md` records the workflow and deferred runtime acceptance.

## Increment 05 — WS02.4 Object Generator with Named Selections

Accepted source evidence:

- `NamedSelectionObjectGeneratorDomain.cs` binds every generator row to exactly one stable named-selection identifier.
- Missing, duplicate and unknown row bindings fail explicitly.
- Named selections are resolved against the active geometry signature before generated objects are returned.
- Stale or empty evaluated scopes fail through the named-selection catalog.
- Generated objects retain the named-selection UUID, resolved entity count and geometry signature for deterministic audit.
- `docs/validation/ws02-4-object-generator-named-selections-contract.md` records the workflow and deferred runtime acceptance.

## Increment 06 — WS03.1 Pump Assembly with Contact

Accepted source evidence:

- `ContactDomain.cs` defines stable pump-assembly contact regions with explicit source and target named-selection identifiers.
- Contact formulations include frictionless, frictional, bonded and no-separation behavior with explicit detection and symmetry semantics.
- Source and target scopes must resolve as current face-based named selections against the active geometry signature.
- Validation rejects identical or overlapping faces, invalid penalty or pinball values, stale scopes and inconsistent friction settings.
- `docs/validation/ws03-1-pump-assembly-contact-contract.md` records the workflow and deferred nonlinear runtime acceptance.

## Increment 07 — WS03.2 Beam Connections

Accepted source evidence:

- `BeamConnectionDomain.cs` defines stable fixed, pinned, translational, rotational and generalized beam connections.
- Reference and mobile ends resolve through current vertex- or edge-based named selections.
- Six translational/rotational degrees of freedom support explicit release semantics and generalized elastic stiffness.
- Validation rejects invalid IDs, names, offsets, stiffness, incompatible release semantics, stale scopes and overlapping ends.
- `docs/validation/ws03-2-beam-connections-contract.md` records the workflow and deferred beam-runtime acceptance.

## Increment 08 — WS04.1 Mesh Convergence

Accepted source evidence:

- `MeshConvergenceDomain.cs` defines stable convergence studies for deformation, stress, strain-energy and reaction quantities.
- Global, scoped and adaptive refinement modes have explicit scope semantics.
- Scoped studies resolve current edge-, face- or body-based named selections against the active geometry signature.
- Refinement points retain ordered element size, node count, element count and monitored result values.
- Validation requires decreasing element size, increasing mesh population, finite results and unique sequence values.
- Convergence requires an explicit relative tolerance and consecutive-pass count.
- `docs/validation/ws04-1-mesh-convergence-contract.md` records the workflow and deferred numerical acceptance.

## Compile gate

Before 50%, verification is limited to source, schema, state-machine and workflow consistency. At exactly 50%, the branch must be compiled and the first ten increments exercised with recorded results before any of them can be promoted from `Source-complete` to `Validated`.
