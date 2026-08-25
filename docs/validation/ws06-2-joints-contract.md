# WS06.2 Joints source/design contract

## Accepted capabilities

- Seven explicit mechanical joint families are modeled: Fixed, Revolute, Cylindrical, Translational, Universal, Spherical and Planar.
- Every joint owns a stable identifier, name, reference named selection, mobile named selection and local coordinate frame.
- The primary local axis may be arbitrarily oriented in 3-D and must be finite and non-zero.
- Universal and Planar joints require a finite non-zero secondary axis orthogonal to the primary axis.
- Joint mobility is deterministic by family: Fixed has no free DOF; Revolute uses local Rz; Cylindrical uses local Tz + Rz; Translational uses local Tz; Universal uses local Rx + Ry; Spherical uses all rotations; Planar uses local Tx + Ty + Rz.
- Elastic stiffness may be assigned only to a mobile degree of freedom and must be finite and non-negative.
- Lower and upper travel/angle limits are optional, finite and ordered with lower < upper.
- Active limits require a finite positive stop stiffness; stop stiffness without a limit is rejected.
- Duplicate DOF settings and unknown mobility flags are rejected deterministically.
- Reference/mobile scopes may use vertices, edges or faces and are resolved against the active geometry signature.
- A joint cannot connect a named selection to itself or use overlapping reference/mobile entities of the same topology type.
- Duplicate joint identifiers and case-insensitive names are rejected by the catalog.

## Deterministic validation fixtures

1. Mobility mapping is checked for all seven joint families.
2. Axial local frame with arbitrary primary axis is accepted.
3. Two-axis orthogonal local frame is accepted for frame-dependent joints.
4. Limited revolute stiffness is accepted on local Rz.
5. Translational elastic stiffness is accepted on local Tz.
6. Zero primary axis is rejected.
7. Collinear primary/secondary axes are rejected.
8. DOF data on a constrained degree of freedom is rejected.
9. Reversed lower/upper limits are rejected.
10. Stop stiffness without an active travel/angle limit is rejected.

## Source evidence

`windows/AsterMax.MechanicalGui/JointDomain.cs`

`windows/AsterMax.MechanicalGui.DomainSmoke/Program.cs`

## Runtime boundary

This increment certifies the joint data model, local-frame semantics, mobility map, elastic/limit semantics and deterministic validation. It does **not** claim that the finite-element solver already enforces these joints. Solver translation to constraint/MPC formulations and physical reaction, rigidity and kinematic benchmark validation remain mandatory before joints can be marked runtime-complete.
