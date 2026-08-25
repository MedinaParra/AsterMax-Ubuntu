# Runtime rigid Remote Displacement certification

## Certified slice

This gate targets **fully prescribed rigid Remote Displacement on face-based named selections** for the native general-CAD TET4 path.

The runtime is intentionally linearized:

- translations are in mm;
- rotations are in radians;
- all six translation/rotation components must be explicitly prescribed;
- rotation-vector magnitude must not exceed 0.1 rad;
- coupling must be `Rigid` with uniform weighting.

This does not certify partial/free remote DOFs, deformable Remote Displacement, large rotations, free remote-point dynamics, joints or nonlinear contact.

## Kinematic mapping

For every scoped mesh node at position `x_i`, remote point `x_r`, prescribed remote translation `U` and small rotation vector `theta`, the target nodal displacement is

`u_i = U + theta x (x_i - x_r)`.

Each target component is translated into an existing exact mesh-node constraint equation against one node of the zero-valued fixed support:

`u_i,dof - u_anchor,dof = target_i,dof`.

Because the anchor DOF is part of the solver's fixed support, the existing `GeneralCadTet4Solver` MPC reduction eliminates the zero-valued anchor term and the Schur-complement kernel enforces the non-zero prescribed displacement exactly.

No penalty stiffness and no synthetic displacement field are used.

## Real benchmark

The Windows gate generates an OpenCASCADE STEP body (80 x 50 x 20 mm box with two cylindrical holes), meshes it using Gmsh 4.15.2, fixes the minimum-X face and applies rigid Remote Displacement to the maximum-X face.

Prescribed global remote kinematics:

- translation `(0.020, -0.010, 0.005) mm`;
- rotation `(0.0008, -0.0005, 0.0012) rad`.

A non-zero verification surface load `(0, 500, -175) N` is applied so the current static solver follows its already-certified non-zero-load route while the MPC rows prescribe the remote-face kinematics.

## Acceptance gates

1. Windows Release build passes.
2. Existing static/modal/thermal regression passes.
3. WS06 and exact MPC regressions pass.
4. Remote Force and Remote Moment real TET4 regressions pass.
5. STEP generation and real Gmsh TET4 meshing succeed.
6. Exactly three translational MPC equations are emitted per scoped node.
7. MPC anchor belongs to the zero-valued support and lies outside the remote scope.
8. All emitted constraint equations remain active in the native TET4 solve.
9. Maximum MPC residual <= 1e-8.
10. Maximum node-by-node error from `U + theta x r` <= 2e-8 mm.
11. Maximum linear-solve residual <= 2e-7.
12. Displacement and von Mises stress are finite and positive.
13. Local coordinate translation/rotation transforms match their expected global vectors within 1e-14.
14. Partial six-DOF definitions are rejected in this runtime slice.
15. Deformable coupling is rejected in this runtime slice.
16. Rotation magnitude above 0.1 rad is rejected.

## Current solver boundary

`GeneralCadTet4Solver` still requires a non-zero applied load vector before solving. Therefore this gate certifies rigid Remote Displacement **within a loaded static analysis**, not a displacement-only load step.

The next architecture step is a true six-DOF remote-point layer / zero-load-capable constrained solve. That layer is required before free remote DOFs and Joint runtime can be certified.
