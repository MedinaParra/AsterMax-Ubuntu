# Runtime deformable Remote Moment certification

## Certified slice

This gate targets **deformable Remote Moment on face-based named selections** for the native general-CAD TET4 path.

It does not certify rigid remote coupling, Remote Displacement, remote-point rotational DOFs, joints, or nonlinear contact.

## Translation path

`RemoteBoundaryConditionDefinition`
→ current face `NamedSelection`
→ active CAD surface triangles
→ global requested moment
→ shared weighted minimum-norm remote-resultant transfer
→ equivalent non-zero `CadSurfaceForce` entries with zero resultant force
→ existing sparse `GeneralCadTet4Solver`.

No parallel structural solver or synthetic result field is used.

## Pure-couple requirement

For triangle centroids `r_i` measured from the remote point and equivalent triangle forces `f_i`, the transfer enforces:

- `sum(f_i) = 0`
- `sum(r_i x f_i) = M_remote`

The shared transfer kernel solves

`f = W A^T (A W A^T)^-1 b`

with dimensionally scaled moment rows and pivot/rank rejection rather than silent regularization.

## Solver extension

The static TET4 solver now accepts a non-zero nodal load vector even when the resultant applied force is zero. It also reports:

- applied resultant moment;
- support-reaction resultant moment;
- global moment-equilibrium error.

The moment balance is calculated from the actual nodal load and reaction vectors, not from the requested Remote Moment metadata.

## Real benchmark

The Windows workflow generates an OpenCASCADE STEP body (80 x 50 x 20 mm box with two cylindrical holes), meshes it with Gmsh 4.15.2, fixes the minimum-X face and scopes the Remote Moment to the maximum-X face.

The global requested pure moment is `(4500, -3200, 6100) Nmm`. The remote point is offset from the loaded-face centroid by +13 mm in Y and -9 mm in Z.

## Acceptance gates

1. Windows Release build passes.
2. Existing static/modal/thermal solver smoke passes.
3. WS06 and exact MPC regressions pass.
4. Remote Force still passes after migration to the shared transfer kernel.
5. STEP generation and real Gmsh TET4 meshing succeed.
6. Remote Moment emitted force resultant <= 1e-8 N.
7. Remote Moment force-conservation error <= 1e-10.
8. Remote Moment moment-conservation error <= 1e-10.
9. Local coordinate-frame transform error <= 1e-12.
10. Rigid Remote Moment is rejected explicitly.
11. TET4 displacement and von Mises results are finite and positive.
12. PCG relative residual <= 2e-6.
13. Global force-equilibrium error <= 5e-5.
14. Global moment-equilibrium error <= 5e-5.
15. Solver-computed applied moment matches the requested pure moment within 1e-10 relative error.

## Remaining runtime work

- Remote Displacement;
- rigid remote-point kinematics and rotational DOFs;
- joints on the MPC/remote-point layer;
- nonlinear contact;
- independent cross-solver validation.
