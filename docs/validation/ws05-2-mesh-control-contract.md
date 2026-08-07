# WS05.2 Mesh Control source/design contract

## Accepted capabilities

- Controls are owned by one stable mesh identifier and bound to the active geometry signature.
- Body, face and edge sizing use explicit typed scopes and positive element sizes.
- Sphere-of-influence controls require both a positive radius and local element size.
- Inflation controls require face scope, layer count, growth rate and first-layer height.
- Refinement controls use deterministic levels 1 through 3.
- Hard and soft sizing behavior is explicit.
- Scope topology is validated by control kind; empty, duplicate and negative entities are rejected.
- Duplicate control identifiers and case-insensitive names within one mesh are rejected.
- A control cannot be attached to a different mesh or geometry revision.

## Deterministic rejection fixtures

1. Empty control or mesh identifier.
2. Stale or missing geometry signature.
3. Unsupported control kind or sizing behavior.
4. Incompatible entity scope for the selected control kind.
5. Non-positive or non-finite element size, radius or first-layer height.
6. Inflation layer count outside 1–100 or growth rate outside 1.0–2.0.
7. Refinement level outside 1–3.
8. Duplicate topology entities, control identifiers or names.
9. Mesh ownership or geometry-signature mismatch.

## Source evidence

`windows/AsterMax.MechanicalGui/MeshControlDomain.cs`
