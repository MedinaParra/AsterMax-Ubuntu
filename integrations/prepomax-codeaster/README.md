# PrePoMax + Code_Aster integration

This directory contains the first integration layer for running Code_Aster from the PrePoMax analysis GUI without removing or changing the existing CalculiX path.

## Upstream baseline

- Repository: `tsvilans/PrePoMax`
- Branch: `master`
- Pinned commit: `3669e65581650e5d9d868aa761db9efd856f8571`
- License: GPL-3.0 (the integration must remain license-compatible when distributed with PrePoMax-derived code)

The user repository does not currently contain a writable fork of `tsvilans/PrePoMax`, therefore this branch stores a reproducible overlay/patch. `tools/bootstrap.py` checks out the pinned upstream revision and applies this integration locally.

## Architecture

PrePoMax currently treats an `AnalysisJob` as a CalculiX job. The integration introduces a higher-level analysis engine:

```
PrePoMax model / mesh / GUI
          |
          +--> CalculiX (existing path, unchanged)
          |
          +--> Code_Aster
                  |-- .med       mesh
                  |-- .comm      command file
                  |-- .export    as_run study definition
                  |-- .mess      solver log/status
                  `-- .rmed      result database
```

`SolverTypeEnum` in PrePoMax is intentionally **not** reused: it selects the CalculiX matrix solver (Spooles/Diagonal/PaStiX), not the FEA engine.

## Implemented in this milestone

- `AnalysisSolverTypeEnum`: `Calculix` or `CodeAster`.
- Code_Aster settings model (`as_run`, Python/catalog interpreter, work directory, CPU/memory/time limits, version and environment variables).
- Global `SettingsContainer.CodeAster` section with backward-compatible loading of old settings files.
- Code_Aster job file generator for `.export` and `.comm`.
- `AnalysisJob` execution semantics for `.comm/.export/.mess/.rmed`, while retaining `.inp/.sta/.cvg/.frd` for CalculiX.
- Dynamic Code_Aster command catalog discovery from the installed `code_aster.Cata.Commands` package.
- Searchable WinForms command-catalog window available from the Analysis property-grid context menu.
- Solver selector, CPU count and Code_Aster resource limits exposed in the Analysis property grid.
- Automatic switch of executable/arguments/work directory/resource values when `Analysis solver` changes.
- Idempotent source patcher and bootstrap script pinned to the reviewed PrePoMax commit.

## Code_Aster command coverage

The catalog is **not hard-coded** to one Code_Aster release. `scripts/codeaster_catalog.py` queries the actual installed package and returns the available command modules as JSON. This means the GUI can expose commands present in the user's installed Code_Aster version, including future additions.

The integration also recognizes the common mechanical workflow operators:

- Study: `DEBUT`, `POURSUITE`, `FIN`
- Mesh/model: `LIRE_MAILLAGE`, `ASSE_MAILLAGE`, `MODI_MAILLAGE`, `AFFE_MODELE`
- Materials: `DEFI_MATERIAU`, `AFFE_MATERIAU`
- Mechanical loads/BCs: `AFFE_CHAR_MECA`, `AFFE_CHAR_MECA_F`
- Thermal loads/BCs: `AFFE_CHAR_THER`, `AFFE_CHAR_THER_F`
- Linear mechanics: `MECA_STATIQUE`
- Nonlinear mechanics: `STAT_NON_LINE`
- Modal/eigen: `CALC_MODES`
- Dynamics: `DYNA_VIBRA`, `DYNA_NON_LINE`
- Thermal: `THER_LINEAIRE`, `THER_NON_LINE`
- Fields/results: `CALC_CHAMP`, `CREA_CHAMP`, `CREA_RESU`, `IMPR_RESU`

Everything else discovered in the installed catalog remains available through the catalog/advanced command path.

## Bootstrap

Prerequisites: Git, Python 3, Visual Studio with the .NET Framework toolchain required by this PrePoMax revision, and a working Code_Aster installation (`as_run`).

```bash
cd integrations/prepomax-codeaster
python tools/bootstrap.py --destination ../../build/PrePoMax-CodeAster
```

After building the patched source, configure the `Code_Aster` section in PrePoMax Settings. In an Analysis job choose `Analysis solver = CodeAster`. The GUI then switches the job to the configured `as_run`, working directory, CPU, memory, time-limit and version values.

The Analysis property-grid context menu contains `Code_Aster command catalog...`. It runs the catalog helper with the configured Code_Aster Python interpreter and displays the operators actually available in that installation.

## Execution semantics

CalculiX remains:

```text
ccx <existing PrePoMax argument convention>
```

Code_Aster becomes:

```text
as_run <job-name>.export
```

The runner generates the `.export` study definition from the selected job settings. A Code_Aster job is considered to have produced a native result when `<job-name>.rmed` exists. Live/diagnostic status is read from `<job-name>.mess`; fatal Code_Aster diagnostics are treated separately from CalculiX `*ERROR` output.

## Important current boundary

This milestone makes the **GUI selection/settings, Code_Aster runner semantics, study files and dynamic command catalog** real. Native PrePoMax post-processing is still FRD-oriented. Code_Aster produces MED/RMED, so visualizing Code_Aster fields inside the existing PrePoMax result tree requires the next adapter: `RMED -> CaeResults` (preferred) or a controlled conversion layer. The integration deliberately does not fake FRD results.

A full semantic translation of every PrePoMax material/load/contact/step object into every Code_Aster operator is also larger than a keyword substitution. The included `.comm` builder supports a real 3D elastic linear-static study plus an advanced raw-command body. Additional translators should be added by PrePoMax object type while the dynamic catalog keeps all installed Code_Aster commands discoverable.

## Design rule

Do not modify CalculiX behavior to make Code_Aster work. New solver-specific behavior belongs behind `AnalysisSolverTypeEnum` and Code_Aster services. This keeps existing PrePoMax projects backward-compatible and makes future engines possible.