# WS05.1 Mesh Creation — source/design contract

## Accepted capabilities

- Stable mesh and owning-analysis identifiers.
- Active geometry-signature binding with stale-geometry rejection.
- Positive global/minimum element sizing and bounded growth rate.
- Explicit automatic, tetrahedral, sweep, multizone, surface and line methods.
- Linear and quadratic element order.
- Tetrahedron, hexahedron, wedge, pyramid, triangle, quadrilateral and beam families.
- Deterministic method/family compatibility validation.
- Unique body scoping and one mesh definition per analysis.
- Optional generated node/element statistics with positive-count validation.

## Source evidence

`windows/AsterMax.MechanicalGui/MeshCreationDomain.cs`

## Runtime gate

This increment reaches the aggregate 50% gate and therefore requires branch compilation and smoke validation before promotion to runtime-validated status.
