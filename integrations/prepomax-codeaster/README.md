# PrePoMax + Code_Aster integration

This directory contains a reproducible Code_Aster integration for the PrePoMax analysis GUI without removing or changing the existing CalculiX path.

## Upstream baseline

- Repository: `tsvilans/PrePoMax`
- Branch: `master`
- Pinned commit: `3669e65581650e5d9d868aa761db9efd856f8571`
- License: GPL-3.0 (the integration must remain license-compatible when distributed with PrePoMax-derived code)

The user repository does not currently contain a writable fork of `tsvilans/PrePoMax`, therefore this branch stores a reproducible overlay/patch. `tools/bootstrap.py` checks out the pinned upstream revision and applies the integration stages locally.

## Architecture

```text
PrePoMax GUI / FeModel / FeMesh
          |
          +--> CalculiX (existing path)
          |       .inp -> ccx -> .frd/.sta/.cvg
          |
          +--> Code_Aster adapter
                  FeMesh -> native ASTER .mail
                  FeModel -> .comm
                  job settings -> .export
                  as_run -> .mess + .rmed + .resu
                              |
                              v
                    CodeAsterResultBridge
                              |
                              v
                        CaeResults / VTK

Generated studies can also be executed through:

          AsterMax Solver Harness
          preflight -> solver -> artifact/result contracts -> JSON report
```

`SolverTypeEnum` in PrePoMax is intentionally **not** reused: it selects the matrix solver inside CalculiX. `AnalysisSolverTypeEnum` is the higher-level FEA engine selector (`Calculix` / `CodeAster`).

## Implemented

- Analysis solver selector in the Analysis property grid.
- Code_Aster settings: `as_run`, catalog Python, working directory, CPUs, memory, time limit, version and environment variables.
- Backward-compatible defaults: existing PrePoMax projects remain CalculiX unless Code_Aster is selected.
- Code_Aster execution semantics for `.comm/.export/.mess/.rmed/.resu`.
- Native ASTER text mesh writer (`.mail`) generated directly from `FeMesh`; no HDF5/MED input dependency is required.
- Node-set, element-set and part export as Code_Aster groups.
- Solid surface export as real boundary-face elements, using PrePoMax `FeSurface.ElementFaces` and each element's face-node mapping.
- `FeModel -> Code_Aster` semantic translator for the first mechanical scope:
  - 3-D TETRA/HEXA/WEDGE, linear and quadratic;
  - isotropic elastic materials (`Elastic` and `ElasticWithDensity`), optional density;
  - solid-section material assignments;
  - `FixedBC`;
  - prescribed translational `DisplacementRotation` DOFs;
  - concentrated nodal loads (`CLoad`);
  - surface pressure (`DLoad`);
  - gravity (`GravityLoad`);
  - linear `StaticStep` -> `MECA_STATIQUE`;
  - `CALC_CHAMP` and MED result output for displacement, stress, equivalent stress and strain.
- Unsupported model entities generate explicit translation warnings or a hard `NotSupportedException`; they are never silently approximated.
- Old `.rmed/.resu/.mess/.comm/.mail/.export` files are deleted before a Code_Aster run so stale output cannot be mistaken for a successful analysis.
- Dynamic Code_Aster command catalog read from the installed `code_aster.Cata.Commands` package.
- Searchable WinForms command-catalog window.
- `CodeAsterResultBridge` maps deterministic nodal `.resu` tables to native PrePoMax `DISP`, `STRESS` and `TOSTRAIN` fields while RMED remains the complete Code_Aster result database.
- `Field.ComputeInvariants()` is reused for displacement magnitude, Von Mises, Tresca and principal stress invariants.
- A solver-neutral AsterMax execution harness under `harness/` validates inputs, clears stale outputs, executes the solver, validates required artifacts/result tables and writes a SHA-256 traceable JSON report.
- Reproducible bootstrap and Windows GitHub Actions build against the pinned PrePoMax source.

## Code_Aster command coverage

The command list is **not hard-coded**. `scripts/codeaster_catalog.py` imports the actual installed `code_aster.Cata.Commands` module and returns the operators exposed by that installation. Therefore the GUI catalog follows the selected Code_Aster release instead of freezing one version's command list.

Typical operators discoverable through this path include `DEBUT`, `FIN`, `LIRE_MAILLAGE`, `DEFI_GROUP`, `AFFE_MODELE`, `DEFI_MATERIAU`, `AFFE_MATERIAU`, `AFFE_CHAR_MECA`, `MECA_STATIQUE`, `STAT_NON_LINE`, `CALC_MODES`, `DYNA_VIBRA`, `THER_LINEAIRE`, `CALC_CHAMP`, `CREA_TABLE`, `IMPR_TABLE` and `IMPR_RESU`.

All other commands found in the installed catalog remain visible through the advanced catalog path even when a dedicated PrePoMax semantic adapter has not yet been implemented for them.

## Generated Code_Aster study

For a supported PrePoMax static model the run path produces:

```text
<job>.mail     native ASTER mesh and groups
<job>.comm     Code_Aster commands translated from FeModel
<job>.export   as_run study definition
<job>.mess     diagnostic/status output
<job>.rmed     complete MED result database
<job>.resu     deterministic nodal interoperability tables for CaeResults
```

The `.comm` follows this structure:

```python
DEBUT()
mesh = LIRE_MAILLAGE(FORMAT='ASTER', UNITE=20)
model = AFFE_MODELE(... MODELISATION='3D' ...)
# DEFI_MATERIAU / AFFE_MATERIAU
# AFFE_CHAR_MECA from PrePoMax BCs and loads
result = MECA_STATIQUE(...)
result = CALC_CHAMP(...)
IMPR_RESU(FORMAT='MED', UNITE=80, ...)
# CREA_TABLE / IMPR_TABLE for the deterministic CaeResults bridge
FIN()
```

## AsterMax Solver Harness

`harness/astermax_harness.py` is the execution/verification boundary for generated studies. It supports both `code_aster` and `calculix` profiles and is deliberately independent from the GUI.

A run is accepted only if preflight, process and result contracts all pass. For Code_Aster this currently includes non-empty `.mess`, `.rmed` and `.resu`, absence of configured fatal markers, and the five result sections consumed by `CodeAsterResultBridge`: `PPM_DEPL`, `PPM_STRESS_N`, `PPM_STRESS_S`, `PPM_STRAIN_N` and `PPM_STRAIN_S`. Numeric table validation rejects missing components, non-finite values, duplicate nodes and inconsistent node sets.

The harness writes `<job>.harness.json` with exact command, timestamps, exit code, checks, removed stale files and SHA-256 fingerprints for all solver inputs and outputs. See `harness/README.md` and the example manifests.

## Real solver proof

This integration now has a real numerical proof, not only source markers or mocked outputs.

GitHub Actions run **33749269612** executed a physical four-node tetrahedral linear-static case with pinned `simvia/code_aster:17.4.0`. The real Code_Aster process generated `.mess`, `.rmed` and `.resu`; the AsterMax harness returned `PASS` and all five displacement/stress/strain tables passed the numeric contracts.

The same `.rmed/.resu` produced on Linux were downloaded by a Windows job. A clean pinned PrePoMax tree was bootstrapped and built Release/x64, then the production `CodeAsterResultBridge.Read()` path was executed headlessly. The import probe returned exit code **0** and produced native `FeResults`.

Established proof chain:

```text
real Code_Aster 17.4.0
   -> real .mess/.rmed/.resu
   -> AsterMax harness PASS
   -> Windows PrePoMax Release/x64
   -> CodeAsterResultBridge.Read()
   -> FeResults
```

A second `Generated Code_Aster E2E` workflow extends the test boundary to include `FeModel -> CodeAsterModelTranslator.WriteStudy()` so the `.mail/.comm/.export` are generated by the integration itself before the real Code_Aster solve.

## Bootstrap

Prerequisites: Git, Python 3, Visual Studio/.NET Framework toolchain required by the pinned PrePoMax revision, and a working Code_Aster installation (`as_run`) for local real Code_Aster execution.

```bash
python integrations/prepomax-codeaster/tools/bootstrap.py \
  --destination build/PrePoMax-CodeAster
```

The bootstrap runs the solver GUI/job/catalog integration, model translation, results bridge, harness runtime, settings/diagnostics and headless CI probes. GitHub Actions performs the same bootstrap, restores upstream NuGet dependencies, verifies integration markers and compiles `PrePoMax.sln` in Release/x64.

## Current boundary / next layer

The automated semantic translator intentionally targets linear 3-D solid statics. Shells, beams, contacts, plasticity/nonlinear mechanics, modal/dynamic steps and thermal studies still require dedicated translators before they should be generated automatically.

RMED remains the complete solver result database. Phase 1 uses genuine Code_Aster-generated `.resu` tables as the deterministic interoperability bridge into PrePoMax `CaeResults`; a full native RMED reader is still a future improvement.

After the generated-study E2E proof is green, the next validation layer is numerical regression: mesh/input fingerprints, reaction balance, energy checks and explicit reference-solution tolerances.

## Design rule

Do not modify CalculiX behavior to make Code_Aster work. Solver-specific behavior belongs behind `AnalysisSolverTypeEnum` and the `PrePoMax.CodeAster` adapter layer. Execution validation belongs in the solver harness. This preserves existing PrePoMax projects, avoids stale/false-positive results and leaves the architecture open to additional FEA engines later.
