# PrePoMax + Code_Aster integration

This directory contains a reproducible Code_Aster integration for the PrePoMax analysis GUI without removing or changing the existing CalculiX path.

## Upstream baseline

- Repository: `tsvilans/PrePoMax`
- Branch: `master`
- Pinned commit: `3669e65581650e5d9d868aa761db9efd856f8571`
- License: GPL-3.0 (the integration must remain license-compatible when distributed with PrePoMax-derived code)

The user repository does not currently contain a writable fork of `tsvilans/PrePoMax`, therefore this branch stores a reproducible overlay/patch. `tools/bootstrap.py` checks out the pinned upstream revision and applies both integration stages locally.

## Architecture

```text
PrePoMax GUI / FeModel / FeMesh
          |
          +--> CalculiX (existing path)
          |       .inp -> ccx -> .frd/.sta/.cvg
          |
          +--> Code_Aster
                  FeMesh -> native ASTER .mail
                  FeModel -> .comm
                  job settings -> .export
                  as_run -> .mess + .rmed
```

`SolverTypeEnum` in PrePoMax is intentionally **not** reused: it selects the matrix solver inside CalculiX. `AnalysisSolverTypeEnum` is the higher-level FEA engine selector (`Calculix` / `CodeAster`).

## Implemented

- Analysis solver selector in the Analysis property grid.
- Code_Aster settings: `as_run`, catalog Python, working directory, CPUs, memory, time limit, version and environment variables.
- Backward-compatible defaults: existing PrePoMax projects remain CalculiX unless Code_Aster is selected.
- Code_Aster execution semantics for `.comm/.export/.mess/.rmed`.
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
- Old `.rmed/.mess/.comm/.mail/.export` files are deleted before a Code_Aster run so stale output cannot be mistaken for a successful analysis.
- Dynamic Code_Aster command catalog read from the installed `code_aster.Cata.Commands` package.
- Searchable WinForms command-catalog window.
- Reproducible bootstrap and Windows GitHub Actions build against the pinned PrePoMax source.

## Code_Aster command coverage

The command list is **not hard-coded**. `scripts/codeaster_catalog.py` imports the actual installed `code_aster.Cata.Commands` module and returns the operators exposed by that installation. Therefore the GUI catalog follows the selected Code_Aster release instead of freezing one version's command list.

Typical operators discoverable through this path include:

- Study: `DEBUT`, `POURSUITE`, `FIN`
- Mesh/model: `LIRE_MAILLAGE`, `ASSE_MAILLAGE`, `MODI_MAILLAGE`, `DEFI_GROUP`, `AFFE_MODELE`
- Materials: `DEFI_MATERIAU`, `AFFE_MATERIAU`
- Mechanical BC/load: `AFFE_CHAR_MECA`, `AFFE_CHAR_MECA_F`
- Thermal BC/load: `AFFE_CHAR_THER`, `AFFE_CHAR_THER_F`
- Linear/nonlinear mechanics: `MECA_STATIQUE`, `STAT_NON_LINE`
- Modal/dynamic: `CALC_MODES`, `DYNA_VIBRA`, `DYNA_NON_LINE`
- Thermal: `THER_LINEAIRE`, `THER_NON_LINE`
- Fields/results: `CALC_CHAMP`, `CREA_CHAMP`, `CREA_RESU`, `IMPR_RESU`

All other commands found in the installed catalog remain visible through the advanced catalog path even when a dedicated PrePoMax semantic adapter has not yet been implemented for them.

## Generated Code_Aster study

For a supported PrePoMax static model the run path now produces:

```text
<job>.mail     native ASTER mesh and groups
<job>.comm     Code_Aster commands translated from FeModel
<job>.export   as_run study definition
<job>.mess     diagnostic/status output
<job>.rmed     MED result database
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
FIN()
```

Boundary-face elements used for pressure are not included in the `VOLUME_ALL` group, so they are available as geometric support groups without being incorrectly assigned the 3-D volume model.

## Bootstrap

Prerequisites: Git, Python 3, Visual Studio/.NET Framework toolchain required by the pinned PrePoMax revision, and a working Code_Aster installation (`as_run`).

```bash
python integrations/prepomax-codeaster/tools/bootstrap.py \
  --destination build/PrePoMax-CodeAster
```

The bootstrap runs:

1. clone/check out the pinned PrePoMax revision;
2. `apply_overlay.py` for solver GUI/job/catalog integration;
3. `apply_model_translation.py` for `FeModel/FeMesh` translation and `Controller.RunJob` dispatch.

GitHub Actions performs the same bootstrap, restores upstream NuGet dependencies, verifies integration markers and compiles `PrePoMax.sln` in Release/x64.

## Current boundary / next layer

Native PrePoMax post-processing is still primarily FRD-oriented. Code_Aster produces RMED. The next major adapter is therefore:

```text
Code_Aster .rmed
      -> result bridge
      -> CaeResults.FeResults
      -> existing PrePoMax VTK/result tree
```

The current translator intentionally limits automated execution to linear 3-D solid statics. Shells, beams, contacts, plasticity/nonlinear mechanics, modal/dynamic steps, thermal studies and other Code_Aster capabilities remain visible in the dynamic command catalog but require dedicated semantic translators before they should be generated automatically.

## Design rule

Do not modify CalculiX behavior to make Code_Aster work. Solver-specific behavior belongs behind `AnalysisSolverTypeEnum` and the `PrePoMax.CodeAster` adapter layer. This preserves existing PrePoMax projects and leaves the architecture open to additional FEA engines later.
