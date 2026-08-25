# WS06.4 Constraint Equations source/design contract

## Accepted capabilities

- Linear multi-point constraint equations are represented as an explicit sum of coefficient × degree-of-freedom terms equal to a finite right-hand side.
- Mesh-node and remote-point targets are strongly distinguished.
- Solid mesh-node terms permit translational DOFs only; remote-point terms permit translational and rotational DOFs.
- Mesh-node IDs must be positive and remote-point object IDs must be stable non-empty GUIDs.
- Every term coefficient must be finite and non-zero.
- Every constraint equation contains at least two terms; single-term prescribed values belong to boundary-condition semantics instead.
- Duplicate target/DOF terms are rejected rather than silently combined or cancelled.
- Translation-only and rotation-only equations are dimensionally direct.
- Equations mixing translations and rotations require a finite positive length scale so rotational coefficients can be converted to equivalent displacement dimensions before algebraic assembly.
- A mixed-DOF length scale is rejected when it is not required.
- The equation can emit dimensionally scaled terms for downstream matrix/MPC translation.
- Duplicate stable IDs and case-insensitive equation names are rejected by the catalog.

## Deterministic validation fixtures

1. Two-node translational tie equation is accepted.
2. Two remote-point rotational tie equation is accepted.
3. Mixed translation/rotation compatibility equation with length scale is accepted.
4. Mixed-dimensional scaling is numerically checked.
5. Single-term equation is rejected.
6. Zero coefficient is rejected.
7. Duplicate target/DOF terms are rejected.
8. Rotational DOF directly on a solid mesh node is rejected.
9. Mixed translation/rotation equation without length scale is rejected.
10. Length scale on a translation-only equation is rejected.
11. Invalid mesh-node ID is rejected.
12. Non-finite right-hand side is rejected.

## Source evidence

`windows/AsterMax.MechanicalGui/ConstraintEquationDomain.cs`

`windows/AsterMax.MechanicalGui.DomainSmoke/Program.cs`

## Runtime boundary

This increment certifies the algebraic constraint model, dimensional scaling and deterministic validation. It does **not** yet claim that these equations are condensed, augmented or enforced in the global finite-element system. A solver-level MPC implementation plus analytical and reaction-equilibrium benchmarks remain mandatory before Constraint Equations can be marked runtime-complete.
