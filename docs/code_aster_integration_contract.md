# AsterMax Code_Aster Integration Contract

Status: engineering integration specification, not solver validation.

## Scope

AsterMax treats Code_Aster as a scientific solver with explicit data and physics contracts. Passing software tests is not equivalent to a verified FEA result.

## Evidence states

The following states remain independent:

- runtime_verified: the packaged Code_Aster launcher/configuration is identified and executable.
- fea_solve_executed: a real run_aster study returned success and produced a new non-empty result MED.
- numerical_verification: result quantities pass an analytical or authoritative Code_Aster verification case within declared tolerances.
- industrial_validation: the workflow has been validated for a stated engineering application domain.
- results_verified: result content/provenance and declared physical checks have passed.
- ansys_equivalence: false unless a separate benchmark program demonstrates it; AsterMax must not infer this from UI similarity or solver execution.

## Unit system

Current PMV contract is coherent mm / N / MPa:

- geometry and displacement: mm
- force: N
- stress, pressure, Young modulus and surface traction: N/mm^2 = MPa

Code_Aster does not impose a universal unit system; AsterMax is responsible for consistency.

## Mesh contract

Production solid path is quadratic 3-D tetrahedral:

- volume: TET10
- boundary: TRI6
- MED file transport
- one volume semantic group: SOLID
- separate support and load boundary groups

GROUP_MA/GROUP_NO names are restricted by AsterMax to 24 characters because the Code_Aster command catalog accepts character strings of length <= 24 for these keywords. A broader MED name capacity is not used as the solver-facing contract.

A MED is solver-eligible only after an independent file-level verification proves:

1. requested semantic group names exist in the MED family table;
2. each group maps to one distinct family identifier;
3. element FAM membership has the expected element count;
4. support and load face sets do not overlap;
5. the MED hash used to build the study is recorded.

The current C8.2 writer intentionally targets meshio 5.3.5. Its MED backend writes cell_data['cell_tags'] to per-element FAM datasets and mesh.cell_tags to FAS/<mesh>/ELEME family/group names. The exact meshio version is pinned because this behavior is part of an external solver-file contract.

## Model contract

Current first-solve target:

- AFFE_MODELE
- PHENOMENE='MECANIQUE'
- MODELISATION='3D'
- small-displacement linear elasticity only

No nonlinear/contact/material-plasticity claim is allowed from this path.

## Material contract

Initial material model:

- DEFI_MATERIAU(ELAS=...)
- Young modulus in MPa
- Poisson ratio dimensionless and -1 < NU < 0.5
- AFFE_MATERIAU over the modeled solid

## Boundary-condition contract

AsterMax must preserve the distinction between a user-requested resultant force and Code_Aster surface traction.

For a uniform traction load:

requested resultant [N] -> verified selected surface area [mm^2] -> traction [N/mm^2] -> reintegrated resultant check -> FORCE_FACE

AsterMax must not pass a total force directly as FORCE_FACE components.

Fixed support for the initial benchmark is expressed with DDL_IMPO on the verified support GROUP_MA.

## Solve contract

Initial solve command is MECA_STATIQUE. A real solve is acknowledged only when:

1. runtime launcher is verified;
2. .export, .comm and input MED hashes are recorded;
3. result MED does not pre-exist;
4. run_aster is actually invoked;
5. process returns code 0;
6. a new non-empty result MED is created;
7. result MED hash is recorded.

A successful process alone does not set results_verified=true.

## Result-field contract

Code_Aster field localization must be preserved. AsterMax must distinguish, and never silently equate:

- ELGA: integration/Gauss-point fields
- ELNO: element-node fields
- NOEU: nodal fields

AsterMax's existing incident-element maximum visualization projection is a display operation only. It is not a Code_Aster recovered nodal stress and must never be labeled SIGM_NOEU or SIEQ_NOEU.

The first genuine solve should export displacement plus explicitly requested stress/criterion fields with their original localization metadata.

## Numerical verification contract

Before results_verified can become true for the reference structural case, the harness must check at minimum:

- finite displacements and stresses;
- displacement direction/sign consistent with loading;
- reaction/resultant equilibrium against applied load within a declared tolerance;
- no fatal solver diagnostic;
- comparison against an analytical solution or authoritative Code_Aster validation case.

The preferred progression is:

1. constant-strain/patch-style case;
2. axial bar or prismatic traction case;
3. cantilever displacement benchmark;
4. mesh refinement/convergence check.

## Known open gates

- C8.2 MED family writer must pass isolated Windows CI.
- Native Windows Code_Aster runtime payload is not yet qualified in installed AsterMax.
- No genuine Code_Aster solve has yet been evidenced in this integration chain.
- Reaction extraction and equilibrium verification are not yet implemented.
- Result MED reader preserving ELGA/ELNO/NOEU localization is not yet integrated.
- Full geometric CAD-face-to-mesh spatial/orientation equivalence remains stronger than the current area/identity gates.
- Contact, nonlinear analysis, bolt pretension and industrial validation remain out of scope.
