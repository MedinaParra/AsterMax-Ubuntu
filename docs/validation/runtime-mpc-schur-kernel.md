# Runtime MPC Schur-complement kernel certification

## Purpose

Move WS06.4 Constraint Equations from a source-only algebra model toward real numerical enforcement without replacing AsterMax's existing sparse SPD/PCG mechanical solver with an indefinite global KKT solve.

## Numerical formulation

For a symmetric positive-definite base system

`K u = f`

and independent linear constraints

`C u = d`,

the kernel performs:

1. base solve `u0 = K^-1 f`;
2. one influence solve per constraint column, `Y = K^-1 C^T`;
3. small dense Schur system `S = C Y`;
4. multiplier solve `S lambda = C u0 - d`;
5. exact correction `u = u0 - Y lambda`.

This preserves the SPD base operator and makes the number of additional large sparse solves proportional to the number of active MPC rows rather than enlarging the global matrix with Lagrange-multiplier DOFs.

## Runtime acceptance benchmarks

### Benchmark A — two-DOF tie

`K = [[2,-1],[-1,2]]`, `f=[1,0]`, `u1-u2=0`.

Analytical constrained result: `u1=u2=0.5`.

Acceptance: both unknowns agree with 0.5 to `1e-12`, the constraint residual is below `1e-12`, and a finite generalized multiplier is recovered.

### Benchmark B — three-DOF constraint chain

`K=I`, `f=[3,0,0]`, with `u1-u2=0` and `u2-u3=0`.

Analytical constrained result: `u=[1,1,1]`.

Acceptance: all unknowns agree with 1.0 to `1e-12`, both rows are simultaneously satisfied, and two generalized multipliers are recovered.

### Benchmark C — dependent-row rejection

Constraint rows `[1,-1]` and `[2,-2]` are linearly dependent.

Acceptance: the Schur factorization must reject the system rather than silently regularizing or returning arbitrary multipliers.

## Engineering safeguards

- finite RHS and solution checks;
- finite non-zero coefficients;
- reduced-system unknown-index bounds;
- row normalization before rank-sensitive Schur construction;
- explicit Cholesky pivot tolerance to detect dependent/ill-conditioned constraint sets;
- maximum base/influence linear residual tracking;
- maximum final constraint residual tracking;
- recovered generalized constraint multipliers.

## Current boundary

This is now a **real numerical MPC enforcement kernel**, not only a data contract. The remaining production step is wiring mesh-node constraint rows from `ConstraintEquationDefinition` into the reduced DOF map of `GeneralCadTet4Solver`, then validating a real TET4 model with force/reaction equilibrium. Remote-point rotational DOFs still require a remote-DOF augmentation/translation layer before they can enter the native TET4 system.
