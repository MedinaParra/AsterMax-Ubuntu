# AsterMax Mechanical roadmap execution ledger

This ledger is the source-level gate for the M01–M08 implementation roadmap. A feature is counted only when its source/design acceptance evidence is present. Compilation and runtime validation remain intentionally deferred until aggregate progress reaches 50%.

## Progress model

The roadmap is divided into 20 workshop-equivalent increments. Each certified increment is worth 5%.

| Increment | Scope | Source/design gate | Runtime gate | Status |
|---|---|---|---|---|
| 01 | WS01.1 Mechanical Basics | Accepted below | Deferred until 50% | Source-complete |
| 02 | WS02.1 2D Gear and Rack | Pending | Deferred until 50% | Pending |
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

**Current source/design progress: 5%.**

## Increment 01 acceptance contract — WS01.1 Mechanical Basics

### Required workflow states

The application model shall expose these states independently of presentation controls:

- `Incomplete`
- `UpToDate`
- `OutOfDate`
- `Solving`
- `Solved`
- `Error`
- `Suppressed`

A parent becomes `OutOfDate` when any dependency changes. A solve may begin only when all mandatory children are complete. Unsupported objects must fail explicitly rather than being ignored.

### Required project operations

- New project.
- Open project.
- Save project.
- Save As.
- Reopen without losing object identity or scope.
- Rename, duplicate, suppress, unsuppress and delete objects.
- Versioned project schema with forward migration hooks.
- Dirty-state tracking independent of solver state.

### Required interaction contract

- Ribbon or menu insertion of analysis objects.
- Outline selection drives Details content.
- Graphics selection can be committed to the active object's scope.
- Both `preselect → insert` and `insert → apply scope` sequences are supported.
- Worksheet and Graph panels can bind to the active object without owning project data.
- UI labels are presentation-only; persistence uses stable type identifiers.

### Unit contract

Canonical storage uses SI. Display systems must include:

- mm–N–MPa;
- m–N–Pa;
- in–lbf–psi.

Every dimensional property stores a quantity type and converts only at the UI or import/export boundary. Unit-system changes must not alter the physical model.

### Persistence contract

The saved project must retain:

- schema version;
- application version;
- stable object IDs;
- parent/child ordering;
- object type IDs;
- names and suppression state;
- geometry references;
- Named Selection references;
- material assignments;
- loads, supports and settings;
- result requests;
- solver-run metadata and hashes when available;
- active unit system and view preferences.

Geometry references must use persistent signatures rather than transient entity indices alone. A signature contains entity type, geometric measure, centroid, bounding box and orientation data with a configurable matching tolerance.

### Source-level verification

The current branch already demonstrates the minimum analysis path needed by this increment:

- a Mechanical-style Ribbon, Outline, Graphics, Details and Worksheet layout;
- STEP geometry import and CAD-face scoping;
- material, support, force, mesh and solution objects;
- a persistent general-CAD TET4 solver path;
- authentic displacement, stress and reaction recovery;
- explicit limitations for unsupported workflows.

The remaining runtime acceptance for this increment is intentionally queued for the first compile gate at 50%.

## Compile gate

Before 50%, verification is limited to source, schema, state-machine and workflow consistency. At exactly 50%, the branch must be compiled and the first ten increments must be exercised with recorded results before any of them can be promoted from `Source-complete` to `Validated`.
