# P0 STEP regression ledger

## Base state and reproduced defect

Branch base: `agent/mechanical-gui-pdf-workflow` at `2165d05dd42c8afb429ebc8c9dda703826fbc5a8`.

Original user regression file: `CILINDRO-SIMPLE.stp`.

- Original uploaded-file SHA-256: `d1c494cd939fe83dbeb71ecee564c3366bab9e9fe1c7408f088966345ad381a1`.
- Size: 4,731 bytes.
- STEP schema: AP214 / automotive design.
- `MANIFOLD_SOLID_BREP`: 1.
- `CLOSED_SHELL`: 1.
- `ADVANCED_FACE`: 3.
- Surface types: two planes + one cylindrical surface.
- Cylindrical radius: `17.0293863659264 mm` after source-unit conversion.
- Expected diameter: `34.0587727318528 mm`.
- Expected axial length: `106.6 mm`.
- Source length unit: metre; internal AsterMax unit: millimetre.

The old `SimpleStepReader.ReadPrismaticSolid` route was reproduced against the original file before the fix. It found 8 textual `CARTESIAN_POINT` entities and produced this incorrect validity envelope:

- X: `0 .. 17.0293863659264 mm`
- Y: `0 .. 0 mm`
- Z: `0 .. 106.6 mm`

Because Y was zero, the old path raised `The imported STEP envelope is not a three-dimensional solid.` before Gmsh/OpenCASCADE could read the valid cylindrical B-Rep. The reproduction itself took approximately 1.3 ms because the failure occurred in text parsing, not OCC.

## P0.1 implementation contract

The general import route now calls Gmsh/OpenCASCADE first. Textual STEP inspection is diagnostic only. `SimpleStepReader` is attempted only after successful OCC validation and only to select the existing verified rectangular-prism optimization; an exception from the legacy reader cannot reject a general B-Rep.

The transactional commit boundary is after all of these checks:

1. Gmsh/OpenCASCADE completed successfully;
2. the surface mesh is non-empty;
3. selectable CAD topology is non-empty;
4. the triangle skin is closed;
5. a positive enclosed volume is recovered;
6. at least one solid is identified.

Until that boundary, the currently displayed model remains untouched.

## P0.2 process contract

Managed Gmsh execution now has a linked user-cancellation token and finite stage timeout. On cancellation or timeout it calls `Kill(entireProcessTree: true)`, waits for real process termination, drains redirected output, and deletes the temporary operation workspace in `finally`.

Default preview timeout: **60 s**. Volume-mesh timeout: **180 s**. Both are configurable through `ASTERMAX_STEP_PREVIEW_TIMEOUT_SECONDS` and `ASTERMAX_STEP_VOLUME_TIMEOUT_SECONDS`.

The GUI operation controller exposes stage/detail, elapsed time and Cancel. The overlay is closed directly in the operation `finally`, and application close is deferred until the active geometry operation has cancelled and released its child process.

## Required STEP regression set

| File | Current status on this branch | Required evidence |
|---|---|---|
| `CILINDRO-SIMPLE.stp` | Implemented fixture; Windows CI verification pending | 1 closed solid, exactly 3 selectable faces, metre→mm conversion, full-diameter bbox, non-empty surface and TET4 mesh, no orphan process |
| `Bolt_Plates.stp` | NotRun | hash, unit, bodies/solids, faces/edges, bbox, volume, OCC/surface/volume times, mesh counts, selection IDs, diagnosis |
| `Bracket.stp` | NotRun | same regression evidence |
| `Cap_fillets.stp` | NotRun | same regression evidence |
| `Flange Mount.stp` | NotRun | same regression evidence |
| `Gear_Set_2D.stp` | NotRun | same regression evidence; classify 2D behavior precisely |
| `Machine_Frame.stp` | NotRun | same regression evidence |
| `Mesh_Arm_2.stp` | NotRun | same regression evidence |
| `Pump_assy_3.stp` | NotRun | same regression evidence; classify multi-body/assembly |
| `Pump_housing.stp` | NotRun | same regression evidence |
| `Solenoid_body.stp` | NotRun | same regression evidence |
| `Submodelv150.stp` | NotRun | same regression evidence; classify submodel input |
| `Valve_RM_20130113.stp` | NotRun | same regression evidence |
| `assembly_solid.stp` | NotRun | same regression evidence; classify multi-body/assembly |

No rule requires four or more faces. The cylinder regression is explicitly required to pass with three faces.

## CLI gates

The branch adds:

```text
AsterMax-Mechanical.exe --step-import-smoke <step> --expect-solids 1 --expect-faces 3
AsterMax-Mechanical.exe --step-import-control-smoke <step>
```

The cylinder smoke uses an explicit bbox tolerance of `0.05 mm` for the two diameter directions and axial length. The control smoke forces timeout and cancellation, requires cancellation cleanup within 2 seconds, checks for newly-created orphan Gmsh process IDs, and checks for newly-created leftover temporary workspaces.

## Certification impact

P0 STEP import work does **not** certify any of the 20 Mechanical workshops. Strict curriculum status remains `0/20 = 0%` until exact E2E workshop evidence exists.
