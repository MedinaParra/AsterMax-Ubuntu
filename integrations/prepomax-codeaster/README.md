# PrePoMax + Code_Aster integration

This directory contains the first integration layer for running Code_Aster from the PrePoMax analysis GUI without removing or changing the existing CalculiX path.

## Upstream baseline

- Repository: `tsvilans/PrePoMax`
- Branch: `master`
- Pinned commit: `728878efac852da5b988eeb65385eb2249611eb6`
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
- Code_Aster job file generator for `.export` and `.comm`.
- Dynamic Code_Aster command catalog discovery from the installed `code_aster.Cata.Commands` package.
- Searchable WinForms command-catalog window for the PrePoMax GUI.
- Idempotent source patcher that adds the solver selector to the Analysis property grid and makes `AnalysisJob` execute either CalculiX or Code_Aster conventions.
- Bootstrap script pinned to the reviewed PrePoMax commit.

## Code_Aster command coverage

The catalog is **not hard-coded** to one Code_Aster release. `scripts/codeaster_catalog.py` queries the actual installed package and returns the available command modules as JSON. This means the GUI can expose commands present in the user's installed Code_Aster version, including future additions.

The integration also tags common mechanical workflows as first-class groups:

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

Prerequisites: Git, Python 3, Visual Studio 2022 with the .NET Framework toolchain required by PrePoMax, and a working Code_Aster installation (`as_run`).

```bash
cd integrations/prepomax-codeaster
python tools/bootstrap.py --destination ../../build/PrePoMax-CodeAster
```

To point the generated PrePoMax tree at a specific Code_Aster installation, configure the executable in the Analysis job property grid (`Analysis solver = CodeAster`, `Executable = .../as_run`) or wire the settings class into the global settings UI.

## Execution semantics

CalculiX remains:

```text
ccx -i <job-name>
```

Code_Aster becomes:

```text
as_run <job-name>.export
```

A Code_Aster job is considered to have produced a native result when `<job-name>.rmed` exists. Its diagnostic output is read from `<job-name>.mess`.

## Important current boundary

This milestone makes the **GUI/job runner, Code_Aster case files and command catalog** real. Native PrePoMax post-processing is still FRD-oriented. Code_Aster produces MED/RMED, so visualizing Code_Aster fields inside the existing PrePoMax result tree requires the next adapter: `RMED -> CaeResults` (preferred) or a controlled conversion layer. The integration deliberately does not fake FRD results.

Similarly, a full semantic translation of every PrePoMax load/material/contact/step object into every Code_Aster operator is larger than a one-to-one keyword swap. The included `.comm` builder supports a valid 3D linear-static skeleton and an advanced raw-command body; additional translators should be added by object type while keeping the catalog available for unsupported commands.

## Design rule

Do not modify CalculiX behavior to make Code_Aster work. New solver-specific behavior belongs behind `AnalysisSolverTypeEnum` and Code_Aster services. This keeps existing PrePoMax projects backward-compatible and makes future engines possible.