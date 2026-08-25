# WS06.3 Remote Boundary Conditions source/design contract

## Accepted capabilities

- Remote Displacement, Remote Force and Remote Moment are explicit condition types.
- Every condition owns a stable identifier, name, named-selection scope and finite 3-D remote point.
- Component definition supports translations and rotations with deterministic type compatibility: displacement may prescribe any of six components, force only translational components, and moment only rotational components.
- Remote forces and moments must contain at least one finite non-zero load component; remote displacements may prescribe zero to constrain a DOF.
- Coordinate components may use global axes or an explicitly defined orthogonal local Cartesian frame.
- Rigid and Deformable coupling behaviors are explicit.
- Uniform, area-weighted and distance-weighted distribution are represented; rigid coupling is restricted to uniform weighting.
- Distance weighting requires a finite positive exponent and the exponent is rejected for other weighting modes.
- Scoping is restricted to vertex, edge, face or mesh-node named selections and must resolve against the active geometry signature.
- Duplicate identifiers and case-insensitive names are rejected by the catalog.

## Deterministic validation fixtures

1. Global and orthogonal local frames are accepted.
2. Remote displacement with translational/rotational prescription is accepted.
3. Non-zero remote force is accepted.
4. Non-zero remote moment is accepted.
5. Rigid uniform, deformable area-weighted and deformable distance-weighted coupling are accepted.
6. Global coordinates with local axes are rejected.
7. Local coordinates without both axes are rejected.
8. Collinear local axes are rejected.
9. Rotational components on a Remote Force are rejected.
10. Translational components on a Remote Moment are rejected.
11. All-zero Remote Force is rejected.
12. Distance weighting without a positive exponent is rejected.
13. Non-uniform rigid coupling is rejected.
14. Non-finite components are rejected.

## Source evidence

`windows/AsterMax.MechanicalGui/RemoteBoundaryConditionDomain.cs`

`windows/AsterMax.MechanicalGui.DomainSmoke/Program.cs`

## Runtime boundary

This increment certifies the remote-point data model, coordinate-frame semantics, component compatibility, coupling behavior and deterministic validation. It does **not** claim that distributed remote coupling equations are already assembled into the finite-element system. MPC/constraint translation and force/moment/reaction-equilibrium benchmarks remain mandatory before Remote Boundary Conditions can be marked runtime-complete.
