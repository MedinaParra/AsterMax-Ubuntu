# AsterMax C9.93 — ANSYS Evidence Intake Gate

Purpose: move AsterMax toward defensible ANSYS equivalence without inventing or back-fitting ANSYS values.

Production evidence accepted only when all of the following are true:

- schema = `astermax-ansys-reference/v1`
- solver product = `ANSYS Mechanical`
- solver version recorded
- evidence explicitly marked `independent=true`, `synthetic=false`, `fea_values_invented=false`
- evidence source is an ANSYS export/report and its SHA-256 matches the supplied source file
- model contract units are exactly mm/N/MPa
- model contract SHA-256 is present and matches the Code_Aster comparison contract
- mesh node/element counts are positive
- compared quantities are finite and unit-labelled
- benchmark IDs match
- comparison tolerances are declared before comparison

This gate does NOT make AsterMax globally equivalent to ANSYS. Passing one benchmark only establishes `PROVEN_FOR_THIS_BENCHMARK`. Project-level `ANSYS_EQUIVALENCE = PROVEN` remains forbidden until the benchmark ladder and mandatory domains are independently evidenced.

## B01 intake target

For the first independent reference, run the exact B01 axial HEXA8 bar in ANSYS Mechanical using the same model contract already used by AsterMax/Code_Aster, then export a result file/report and provide:

- ANSYS Mechanical version
- mesh node/element counts
- model contract SHA-256
- requested result quantity and units
- exported source file SHA-256
- the original ANSYS export/report file

No numerical ANSYS result is stored in this repository until it is supplied from a real independent ANSYS run.
