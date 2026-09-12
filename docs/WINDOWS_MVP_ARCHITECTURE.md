# AsterMax Windows PMV — Architecture boundary v0.1

## Objective
Deliver a reproducible Windows-native minimum static structural workflow without requiring Code_Aster for the certified baseline.

## Certified baseline

`STEP/STP in mm -> validation -> Gmsh OCC/TET4 -> internal linear solver -> authentic fields -> equilibrium + analytical benchmark -> report`

The project contract uses N-mm-MPa internally. Any imported CAD geometry must be normalized to millimetres before entering the certified solver boundary.

## Backend policy

- **Gmsh**: native Windows meshing and CAD/OCC adapter.
- **AsterMax internal solver**: mandatory native Windows baseline for linear static TET4.
- **Code_Aster**: advanced backend only; accessed through an adapter (for example WSL2, Linux container/VM, or remote worker) and never required for the baseline PMV to launch, validate or solve its certified reference cases.

## Harness gates

1. Project schema/contract validates units and supported scope.
2. Unsupported features fail explicitly.
3. Analytical reference values are computed independently of FEA.
4. Solver results, once wired, must be compared to the analytical reference with documented tolerances.
5. Force and moment equilibrium must pass before a run can be labelled validated.
6. Every input project receives a canonical SHA-256 fingerprint.
7. Windows CI executes the portable contract on every branch/PR.

## Next vertical slice

Implement `GmshAdapter` to:

1. import STEP/STP through OCC;
2. inspect the CAD bounding box in mm;
3. generate deterministic first-order tetrahedral mesh;
4. expose node coordinates, tetra connectivity and boundary face groups;
5. record Gmsh version and meshing options in the run manifest;
6. add a generated cantilever STEP fixture and verify geometric dimensions before meshing.

No stress contour should be presented as a validated simulation until the mesh and solver paths both pass this harness.
