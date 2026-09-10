# C9.95 — STEP mm Unit Fidelity Preflight

This increment addresses a professional CAE failure mode: importing geometry at the wrong physical scale. The guard inspects STEP unit declarations before AsterMax treats the model as millimetre-native.

## What is proven
- Native `SI_UNIT(.MILLI.,.METRE.)` is accepted as 1.0 mm/mm.
- `SI_UNIT($,.METRE.)` is detected as requiring x1000 rescale to mm.
- Explicit `CONVERSION_BASED_UNIT('INCH',...)` is detected as requiring x25.4 rescale.
- Files with unrecognized/absent length-unit evidence are not allowed to claim direct mm import.

## What is deliberately not claimed
This parser does not prove B-Rep/STEP geometry import, topology healing, tessellation, meshing, solver correctness, or visual rendering. Those remain separate harness gates.

## Integration target
The next native GUI patch should invoke this preflight in the STEP import path and show one of three states before model preparation:
1. `MM_NATIVE` — continue without scaling.
2. `RESCALE_REQUIRED` — apply/confirm the exact scale factor and record it in model provenance.
3. `UNKNOWN` — block professional-demo certification until the user confirms/importer resolves units.

The resulting unit state and scale factor must be included in the model fingerprint so CAD scale cannot silently change between import, mesh and solve.

## Remaining professional gaps
- Real STEP import smoke test with a known bounding box and topology count.
- Deterministic geometry fingerprint after import.
- TET/HEXA mesh quality metrics and bad-element rejection.
- End-to-end native GUI test: geometry -> material -> BC/load -> Code_Aster -> result contours.
- Code_Aster runtime packaging on Windows remains a major deployment gap.
- Independent ANSYS reference is still required before any numerical-equivalence claim.

Status after C9.95: `STEP_UNIT_FIDELITY_GATE_IMPLEMENTED`, not `CAD_IMPORT_PROVEN`.
