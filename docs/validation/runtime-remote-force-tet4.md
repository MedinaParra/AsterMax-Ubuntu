# Runtime deformable Remote Force certification

## Certified slice

This gate certifies **deformable Remote Force on face-based named selections** for the native general-CAD TET4 path.

It does not certify rigid remote coupling, Remote Displacement, Remote Moment or remote-point rotational DOFs.

## Translation path

`RemoteBoundaryConditionDefinition`
→ current face `NamedSelection`
→ active CAD surface triangles
→ global force vector
→ weighted minimum-norm equivalent triangle forces
→ `CadSurfaceForce` entries
→ existing sparse `GeneralCadTet4Solver`.

No parallel solver or synthetic result field is used.

## Equilibrium formulation

For triangle centroids `r_i` measured from the remote point and equivalent triangle forces `f_i`, the translator enforces six equations:

- `sum(f_i) = F_remote`
- `sum(r_i x f_i) = 0`

The weighted minimum-norm solution is

`f = W A^T (A W A^T)^-1 b`

where the selected weighting method defines `W` and `b = [F_remote, 0_moment]`.

The six-by-six system is solved with pivoted elimination and a rank tolerance. A geometrically deficient scope is rejected instead of regularized silently.

## Supported weighting in this slice

- Uniform
- AreaWeighted
- DistanceWeighted with finite positive exponent

The runtime benchmark uses AreaWeighted transfer.

## Real benchmark

The Windows workflow builds an OpenCASCADE STEP body (80 x 50 x 20 mm box with two cylindrical holes), meshes it with Gmsh 4.15.2, fixes the minimum-X face and scopes the Remote Force to the maximum-X face.

The remote point is offset from the loaded-face centroid by +17 mm in global Y and +11 mm in global Z. The requested global force is `(1000, 175, -125) N`.

## Acceptance gates

1. Windows Release build passes.
2. Existing static/modal/thermal solver smoke passes.
3. WS06 and exact MPC regressions pass.
4. STEP generation and real Gmsh TET4 meshing succeed.
5. Remote Force domain definition and active named selection validate.
6. Force conservation error <= 1e-10.
7. Moment conservation error about the remote point <= 1e-10.
8. Equivalent surface-load resultant remains equal to the requested force within 1e-10 relative error.
9. TET4 displacement and von Mises results are finite and positive.
10. PCG relative residual <= 2e-6.
11. Global force equilibrium error <= 5e-5.

## Remaining runtime work

- rigid Remote Force via remote-point/MPC kinematics;
- Remote Displacement;
- Remote Moment and rotational remote DOFs;
- joint translation onto the remote/MPC layer;
- cross-solver physical validation against Code_Aster or another independent reference.
