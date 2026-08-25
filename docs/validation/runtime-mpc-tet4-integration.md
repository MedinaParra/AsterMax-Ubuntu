# Runtime MPC integration in GeneralCadTet4Solver

## Objective

Certify that a real mesh-node `ConstraintEquationDefinition` is translated into the reduced TET4 degree-of-freedom system and enforced by the production sparse solver path.

## Production path under test

`STEP -> OpenCASCADE/Gmsh -> CadMesh TET4 -> fixed-DOF reduction -> CSR stiffness -> PCG K^-1 solves -> Schur MPC enforcement -> displacement/stress/reaction recovery`

No synthetic displacement field is accepted as evidence for this gate.

## Runtime translation contract

- `ConstraintTargetKind.MeshNode` uses one-based external node IDs and maps them to zero-based `CadMesh.Nodes` indices.
- Only TranslationX, TranslationY and TranslationZ can map directly to native solid TET4 DOFs.
- Remote-point terms are explicitly rejected until a remote-DOF augmentation layer exists.
- Terms attached to zero-valued fixed-support DOFs are eliminated from the reduced row.
- A row that becomes empty and has zero RHS is already satisfied and is skipped.
- A row that becomes empty with non-zero RHS is rejected as contradictory with the fixed supports.
- Remaining rows are passed to `MpcSchurComplementKernel` and must satisfy a maximum absolute constraint residual <= 1e-8.

## Real TET4 benchmark

The Windows gate builds an OpenCASCADE STEP model consisting of an 80 x 50 x 20 mm box with two cylindrical holes, meshes it with Gmsh 4.15.2, fixes the minimum-X face and applies a 1000 N axial surface force to the maximum-X face.

The benchmark first solves the unconstrained model. It then searches the loaded face for the translational DOF with the largest displacement spread between free nodes. A compatibility equation `u_A - u_B = 0` is imposed on that real pair and the same TET4 model is solved again.

## Acceptance criteria

1. Windows Release build passes.
2. Existing static/modal/thermal regression passes.
3. Existing WS06 domain and analytical Schur-MPC regressions pass.
4. STEP generation and Gmsh TET4 meshing succeed.
5. The unconstrained benchmark has finite displacement, stress, PCG residual and force equilibrium.
6. The selected unconstrained compatibility gap is > 1e-10 mm, proving the test is not vacuous.
7. Exactly one reduced MPC equation is active.
8. Maximum MPC residual <= 1e-8.
9. The constrained displacement gap <= 1e-8 mm and is at least 1000 times smaller than the baseline gap.
10. Force equilibrium error <= 5e-5.
11. The generalized MPC multiplier is finite.

## Remaining boundary

Passing this gate certifies **mesh-node translational Constraint Equations at runtime**. It does not certify remote-point rotational DOFs, Remote Boundary Conditions, Joints, nonlinear contact, or general assembly coupling. Those capabilities must reuse this runtime foundation and pass their own physical benchmarks.
