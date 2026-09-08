# AsterMax C9.59 — Model Contract → Code_Aster Adapter v0

## Increment delivered
C9.59 introduces the first deterministic translation boundary between an AsterMax-owned model contract and Code_Aster input files. The adapter consumes `astermax-model-contract/v0` JSON in `MM_N_S_MPA` and emits ASTER `.mail`, Code_Aster `.comm`, and an adapter manifest.

## Verified benchmark
The deterministic axial-bar contract uses a 100 × 10 × 10 mm HEXA8 model, E=210000 MPa, nu=0.30, fixed XYZ support on the x=0 face, and 10000 N total axial load distributed over four nodes. The generated solver deck preserves MECA_STATIQUE, CALC_CHAMP, displacement probe, von Mises request and MED export.

The analytical values sigma=100 MPa and ux=0.047619047619047616 mm are reference calculations only. Code_Aster was NOT executed in C9.59 and no FEA result is claimed.

## Validation
`harness-c959-adapter.ps1` gates schema, units, mesh topology, groups, material, support, total load conservation, static solver operators, postprocess contract, no fabricated results, analytical-reference recomputation and semantic parity with C9.58. Current CI result: 12/12 PASS.

## Professional gaps / debt
1. Adapter v0 is external PowerShell and is not yet wired to the native AsterMax model tree.
2. Adapter v0 supports one isotropic material, one fixed support, one nodal-force load and HEXA8 benchmark topology only.
3. Code_Aster execution is not yet integrated in Windows CI/runtime.
4. No real `.med` result has yet been imported into the AsterMax VTK results pipeline.
5. No mesh-quality, convergence, contact, nonlinear or modal validation is claimed.
6. No comparison against ANSYS numerical output is claimed.

## Next priority
C9.60 should implement a native C# bridge from the actual AsterMax/PrePoMax model objects to `astermax-model-contract/v0`, then round-trip that generated contract through the existing C9.59 adapter. A second gate should execute Code_Aster in a controlled environment and compare real solver displacement/stress against the analytical axial-bar tolerance before enabling professional postprocessing claims.
