# WS02.1 — 2D Gear and Rack source/design acceptance

## Purpose

Define the source-level contract for the first M02 workflow without compiling or executing the application before the 50% roadmap gate.

## Required model

- Two active planar bodies representing gear and rack.
- Stable geometry, material and section identifiers.
- Plane-stress formulation with positive thickness.
- Persistent face signatures instead of transient CAD indices.
- At least one explicitly scoped edge pair between the gear and rack.
- Body roles for flexible, rigid and suppressed states.
- A single formulation per analysis system.

## Required workflow sequence

1. Create a Static Structural 2-D analysis.
2. Import or reference planar gear and rack geometry.
3. Assign the plane-stress section and material.
4. Preserve body identity after save/reopen.
5. Scope the gear-to-rack edge pair.
6. Reject incomplete models before translation to a solver backend.
7. Mark the analysis out-of-date when section, material, body role or scope changes.

## Source evidence

`TwoDimensionalAnalysisDomain.cs` defines the formulation, section, planar body, contact-pair and complete-analysis contracts. Validation rejects missing stable IDs, invalid thickness, invalid plane normals, unknown sections, mixed formulations, absent active bodies and absent gear/rack edge scope.

## Deferred runtime gate

At 50% overall progress, the fixture must be compiled and exercised. Runtime acceptance will require a generated 2-D mesh, constrained rigid-body modes, a transmitted contact force and a saved/reopened project with unchanged stable IDs and scopes.
