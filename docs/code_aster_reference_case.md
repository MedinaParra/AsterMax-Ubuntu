# AsterMax Code_Aster Reference Mechanical Case

## Purpose

This case is a numerical-verification problem for the AsterMax -> Code_Aster pipeline. It is not an industrial validation case and it is not an ANSYS equivalence claim.

The target solution is a homogeneous, small-strain, isotropic uniaxial state in a rectangular prism using the AsterMax unit contract mm / N / MPa.

## Closed-form solution

For prism length L, width b, height h, area A=b*h, Young modulus E, Poisson ratio nu, and axial resultant F applied uniformly on x=L:

- sigma_x = F/A
- epsilon_x = sigma_x/E
- u_x(L) = F*L/(A*E)
- epsilon_y = epsilon_z = -nu*epsilon_x
- total support reaction R_x = -F

## Boundary-condition requirement

A fully fixed x=0 face is not accepted for this verification oracle because it suppresses Poisson contraction and introduces a non-homogeneous end constraint. The reference model shall reproduce the homogeneous solution with symmetry constraints:

- X0_SYM: DX = 0 on plane x=0
- Y0_SYM: DY = 0 on plane y=0
- Z0_SYM: DZ = 0 on plane z=0
- LOAD_FACE: uniform FORCE_FACE traction in +X on plane x=L
- SOLID: 3D continuum domain

These three symmetry planes remove rigid-body modes while remaining compatible with the analytical Poisson contraction field.

## Solver-side evidence required before verification may run

1. Real MED input with solver group names and element membership verified.
2. Real `.comm` and `.export` hashes.
3. Real native Windows `run_aster` execution with return code 0.
4. Newly created non-empty result MED with SHA256 provenance.
5. Displacement field extracted from the result, not synthesized.
6. REAC_NODA computed by CALC_CHAMP and resultant extracted on the x=0 support node group.
7. Axial stress obtained from an explicitly declared Code_Aster stress field representation. AsterMax visualization projection is not accepted as solver stress evidence.

## Numerical acceptance

Initial PMV tolerances are explicit harness tolerances, not universal solver accuracy claims:

- end displacement relative error <= 2%
- support reaction relative error <= 0.5%
- axial stress relative error <= 2%
- displacement, reaction and stress signs must agree with the analytical solution

Mesh-convergence work shall tighten or replace these tolerances later. A single passing mesh only verifies this reference case at these stated tolerances.

## Evidence-state rules

Before a genuine solve:

- fea_solve_executed = false
- numerical_verification = false
- results_verified = false
- industrial_validation = false
- ansys_equivalence = false

After a genuine solve, `numerical_verification` and `results_verified` may become true only if all analytical gates pass. `industrial_validation` and `ansys_equivalence` remain false.
