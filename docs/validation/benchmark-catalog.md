# AsterMax deterministic benchmark catalog

All benchmarks are specified before compilation so later implementation cannot tune acceptance criteria after seeing results.

## B001 — axial bar

- Domain: rectangular bar, length 200 mm, section 20 × 20 mm.
- Material: E = 200000 MPa, ν = 0.30.
- Boundary: XMin fixed.
- Load: +10000 N total on XMax.
- Primary reference: `u = F L / (E A)`.
- Acceptance:
  - displacement error ≤ 2%;
  - reaction error ≤ 1e-5 relative;
  - residual ≤ 1e-6.

## B002 — cantilever bending

- Domain: 200 × 40 × 20 mm.
- Material: E = 200000 MPa, ν = 0.30.
- Boundary: XMin fixed.
- Load: -1000 N total in Z on XMax.
- Primary reference: Euler–Bernoulli tip displacement.
- Acceptance:
  - displacement error ≤ 8% for linear TET4 coarse mesh;
  - monotonic improvement under refinement;
  - reaction force and moment error ≤ 1e-4.

## B003 — constant-strain tetrahedron patch

- Domain: conforming tetrahedral partition of a cube.
- Prescribed affine displacement field.
- Expected: constant strain and stress in every element.
- Acceptance:
  - displacement reproduction ≤ 1e-10 relative;
  - element stress spread ≤ 1e-8 relative;
  - no artificial reaction imbalance.

## B004 — surface-force equivalence

- Domain: planar triangulated face with intentionally nonuniform triangle areas.
- Total force: arbitrary vector `(Fx, Fy, Fz)`.
- Expected:
  - sum of nodal forces equals input force;
  - nodal weights equal one third of incident triangle area divided by total area.
- Acceptance: absolute vector difference ≤ 1e-10 N for unit-scale input.

## B005 — perforated plate smoke

- Domain: 80 × 50 × 20 mm block with two through holes.
- Boundary: minimum-X planar face fixed.
- Load: -1000 N in Z on maximum-X planar face.
- Purpose: topology persistence, arbitrary TET4 assembly, PCG, stress recovery and result mapping.
- Acceptance:
  - valid closed mesh;
  - at least 8 selectable CAD faces;
  - positive finite displacement and von Mises;
  - residual ≤ 2e-6;
  - equilibrium error ≤ 2e-5.

## B006 — rigid-body diagnostic

- Domain: free solid with load but no support.
- Expected: controlled failure before or during solve with a rigid-body/singular-system diagnostic.
- Acceptance:
  - no fictitious result;
  - no indefinite execution;
  - diagnostic identifies insufficient constraints.

## B007 — overconstraint consistency

- Domain: bar with compatible zero displacement constraints on both ends and no load.
- Expected: zero displacement, zero stress and zero reactions.
- Acceptance:
  - all fields finite;
  - values ≤ numerical tolerance;
  - no false singularity.

## B008 — unit-system round trip

- Same axial model represented in mm–N–MPa, m–N–Pa and in–lbf–psi.
- Expected: physically identical displacement, stress and reaction after conversion.
- Acceptance: relative difference ≤ 1e-8 after normalization.

## Result record

Each benchmark result must record:

- benchmark ID and schema version;
- application and solver version;
- geometry and mesh hash;
- material, support and load values;
- node, element and free-DOF counts;
- iteration count, residual and equilibrium;
- extrema and reference errors;
- elapsed time and peak memory;
- pass/fail with immutable tolerance values.
