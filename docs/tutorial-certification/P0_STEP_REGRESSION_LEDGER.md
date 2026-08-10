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

## P0.1 implementation

The general import route now calls Gmsh/OpenCASCADE first. Textual STEP inspection is diagnostic only. `SimpleStepReader` is attempted only after successful OCC validation and only to select the existing verified rectangular-prism optimization; an exception from the legacy reader cannot reject a general B-Rep.

The transactional commit boundary is after all of these checks:

1. Gmsh/OpenCASCADE completed successfully;
2. the surface mesh is non-empty;
3. selectable CAD topology is non-empty;
4. the triangle skin is closed;
5. a positive enclosed volume is recovered;
6. at least one solid is identified.

Until that boundary, the currently displayed model remains untouched.

## P0.2 process control

Managed Gmsh execution has a linked user-cancellation token and finite stage timeout. On cancellation or timeout it calls `Kill(entireProcessTree: true)`, waits for real process termination, drains redirected output, and deletes the temporary operation workspace in `finally`.

Default preview timeout: **60 s**. Volume-mesh timeout: **180 s**. Both are configurable through `ASTERMAX_STEP_PREVIEW_TIMEOUT_SECONDS` and `ASTERMAX_STEP_VOLUME_TIMEOUT_SECONDS`.

The GUI operation controller exposes stage/detail, elapsed time and Cancel. The overlay is closed directly in the operation `finally`, and application close is deferred until the active geometry operation has cancelled and released its child process.

## Windows evidence — workflow run #1

Workflow: `AsterMax Windows 2 Beta - STEP P0 Certification`.

Validated source commit: `50a8b7767c68468bdff1a39cb6a32bd10aed064a`.

All workflow stages passed on `windows-latest`: restore, Release build, core prism solver smoke, self-contained `win-x64` publish, bundled Gmsh verification, GUI startup, cylinder STEP smoke, cancel/timeout/no-orphan smoke, evidence creation, portable ZIP packaging and artifact upload.

Cylinder evidence from the real regression fixture:

- Gmsh: `4.15.2`.
- source unit: metre.
- solids: `1`.
- selectable faces: `3`.
- OCC-derived bbox: `34.058773 x 34.055379 x 106.6 mm`.
- recovered surface-mesh volume: `92565.14154 mm^3`.
- surface preview: `143` nodes / `282` triangles.
- volume mesh: `184` nodes / `530` TET4.
- measured preview operation: `619 ms`.
- complete CLI wall clock: `751 ms`.
- forced cancellation cleanup: `8 ms`.
- newly-created orphan Gmsh processes after cancel/timeout: `0`.
- newly-created leftover temporary workspaces after cancel/timeout: `0`.

Portable package:

- file: `AsterMax-Windows-2.0-beta-P0-win-x64.zip`.
- size: `108,066,095 bytes`.
- SHA-256: `27c9ea4f416b124590f524d7ef88ade516075c5f9b6dd37fd2015a6524c9fcd0`.
- executable SHA-256 inside the package: `679f525a98966ba082d0bd553f343fe22b2681466fb37977c02599f2321874e6`.
- GitHub Actions artifact size: `107,739,554 bytes`.
- GitHub Actions artifact digest: `sha256:26e452740bb4cec40d44edb0bb12abd29b04b2adcb53d4070c2f06e36020e0c7`.

## Required STEP regression set

The curricular ZIP `Mechanical_Introduction_17.0_v1.zip` was located and contains 62 entries: 14 STEP/STP inputs, 8 WBPZ projects and 31 PDF files. The 13 additional required STEP files were extracted locally for P0.3 source inventory. Their source hashes are now known; AsterMax Windows OCC/mesh execution is still required before their status can become Passed.

| File | SHA-256 | Current status |
|---|---|---|
| `CILINDRO-SIMPLE.stp` | `d1c494cd939fe83dbeb71ecee564c3366bab9e9fe1c7408f088966345ad381a1` | **Passed P0 regression on Windows** |
| `Bolt_Plates.stp` | `28c5321582fb4441da4976d88d700b2bfb8d7aa2632ec6d97b163f0432b3b391` | NotRun in AsterMax Windows sweep |
| `Bracket.stp` | `ee9ee6319d5c9153960a15fc2f719bb2567797e37f2bc0e0b656dbb94b783110` | NotRun in AsterMax Windows sweep |
| `Cap_fillets.stp` | `4b98de09f4ff958974ebf92e298dde2210b6e2a5bbdddb82a22634ac1e8883c8` | NotRun in AsterMax Windows sweep |
| `Flange Mount.stp` | `89a01cd65d0dc6a1b2014ea1a03eed2297f588cdabe0a385249d3fd4ef663b52` | NotRun in AsterMax Windows sweep |
| `Gear_Set_2D.stp` | `798e0310104322b54261ae3ffe028a24502f21e0a46a0bb65e161cbbd2283a0f` | NotRun in AsterMax Windows sweep |
| `Machine_Frame.stp` | `b46ed073767f89fa261db11bb395e1a7abfeaf2c945664f0ddd896e5b124fdaf` | NotRun in AsterMax Windows sweep |
| `Mesh_Arm_2.stp` | `0958a7ed349b7d757c3687b3d2d7c7c5f556a2f572dcd24535d8b56afa125665` | NotRun in AsterMax Windows sweep |
| `Pump_assy_3.stp` | `d073299876db256ed5db8a00904efa0184ed789007630157bebd3c5df5df755e` | NotRun in AsterMax Windows sweep |
| `Pump_housing.stp` | `3f6c7c9714a7728ed67d4f76fe22d189b8a98fa281af22e767df0571a266d37c` | NotRun in AsterMax Windows sweep |
| `Solenoid_body.stp` | `32a4445fe80850c69f7cbbc01bb706ba9c291aa399cf477aaf6e82f5f01108e2` | NotRun in AsterMax Windows sweep |
| `Submodelv150.stp` | `98365b9ff66f6bac8ade7853981697bef6abac878d8d6631a136194d9a12da4f` | NotRun in AsterMax Windows sweep |
| `Valve_RM_20130113.stp` | `dff5b66f1ffd4dee39e9c3e1658763a0e4df2f14e105897d6e347fc2a6334a1d` | NotRun in AsterMax Windows sweep |
| `assembly_solid.stp` | `5ce198fa86371feec5ecdfbfd860c94d58b788b19227d9795a6bc177e9379709` | NotRun in AsterMax Windows sweep |

No rule requires four or more faces. The cylinder regression passed with exactly three selectable faces.

Independent OpenCASCADE/CadQuery probing has already confirmed that the curricular files are heterogeneous rather than interchangeable: for example `Bracket.stp` imports as shell/compound geometry with zero solid volume, `Gear_Set_2D.stp` has zero textual Z extent, `Bolt_Plates.stp` contains two solids, and `assembly_solid.stp` contains three solids. These independent results are reference/classification evidence only; they do not count as AsterMax Windows `Passed` status.

## CLI gates

```text
AsterMax-Mechanical.exe --step-import-smoke <step> --expect-solids 1 --expect-faces 3
AsterMax-Mechanical.exe --step-import-control-smoke <step>
```

The cylinder smoke uses an explicit bbox tolerance of `0.05 mm` for the two diameter directions and axial length. The control smoke forces timeout and cancellation, requires cancellation cleanup within 2 seconds, checks for newly-created orphan Gmsh process IDs, and checks for newly-created leftover temporary workspaces.

## Remaining P0 / next block

P0.1 and the process layer of P0.2 now have Windows evidence. Remaining work before the environment can be called complete includes the full P0.3 Windows OCC sweep of the other curricular STEP files, explicit UI-level automation for model-preservation/overlay-close exactly-once behavior, removal of the remaining compatibility display dependency on `SimpleStepSolid`, and correction of the legacy fire-and-forget invocation in `ImportGeometry` so the event path awaits the operation directly.

P0 STEP work does **not** certify any of the 20 Mechanical workshops. Strict curriculum status remains **0/20 = 0%** until exact E2E workshop evidence exists.
