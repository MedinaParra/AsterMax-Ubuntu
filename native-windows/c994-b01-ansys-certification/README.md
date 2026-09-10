# C9.94 — B01 Real ANSYS Cross-Solver Certification

Purpose: certify one narrowly defined linear-static benchmark between AsterMax/Code_Aster and an independently executed ANSYS Mechanical model. This package does not contain or fabricate ANSYS results.

## Frozen B01 model
- Solid bar: 100 x 10 x 10 mm.
- Linear isotropic material: E=210000 MPa, nu=0.30.
- x=0 face fixed UX=UY=UZ=0.
- x=100 face total force FX=10000 N.
- Mesh: exactly 10 linear HEXA8 elements along X, 1 x 1 through the cross-section; 44 nodes / 10 elements.
- Primary comparison quantity: arithmetic mean nodal UX on x=100.
- Predeclared ANSYS vs Code_Aster tolerance: <=2.0%.

## Required ANSYS evidence
Run this exact case in ANSYS Mechanical. Export a machine-readable nodal displacement table for the loaded face and preserve the original ANSYS export/report as evidence. C9.93 requires the evidence SHA-256, ANSYS version, independent=true, synthetic=false and fea_values_invented=false.

Do not transcribe a value from a screenshot as the sole evidence. The source file is the evidence and must hash-match the manifest.

## Certification rule
A passing C9.94 result means only `B01 = PROVEN_FOR_THIS_BENCHMARK`. It does not authorize global `ANSYS_EQUIVALENCE=true`.

Current state: `WAITING_FOR_INDEPENDENT_ANSYS_EVIDENCE`.
