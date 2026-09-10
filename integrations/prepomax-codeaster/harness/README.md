# AsterMax Solver Harness

The harness is the execution and verification boundary between an AsterMax/PrePoMax study and a solver process. It is deliberately independent from WinForms so the same analysis contract can be used by the GUI, CI, a command line runner, or a future service.

## Design

```text
PrePoMax / AsterMax GUI
        |
        | generates a solver study
        v
+-----------------------------+
| AsterMax Solver Harness     |
|-----------------------------|
| 1. Manifest + preflight     |
| 2. Input hashes             |
| 3. Remove stale outputs     |
| 4. Execute solver           |
| 5. Process/timeout checks   |
| 6. Artifact contracts       |
| 7. Result contracts         |
| 8. JSON run report          |
+-----------------------------+
       |                 |
       v                 v
   Code_Aster          CalculiX
 .comm/.mail/.export      .inp
       |                 |
     as_run              ccx
       |                 |
 .mess/.rmed/.resu       .frd
       |                 |
       +--------+--------+
                |
                v
        CaeResults / VTK GUI
```

The harness does **not** manufacture, interpolate, or substitute FEA results. It only accepts artifacts actually produced by the configured solver process.

## Fail-closed rules

A solver run is `PASS` only when all configured contracts pass. At minimum this means:

- all required study inputs exist and are non-empty before execution;
- the configured solver executable resolves to a real executable;
- stale solver-owned outputs are deleted before the run;
- the solver does not time out;
- process exit code is zero;
- every required result artifact exists and is non-empty after the run;
- for Code_Aster, the `.mess` file does not contain configured fatal markers;
- for the current Code_Aster result bridge, the `.resu` file contains all required `PPM_*` nodal tables with at least one data row.

A missing `.rmed`, `.resu`, `.frd`, timeout or fatal diagnostic therefore cannot be reported as success simply because the GUI remained responsive.

## Usage

Prepare a generated study directory and copy/adapt one of the example manifests.

Code_Aster preflight only:

```bash
python integrations/prepomax-codeaster/harness/astermax_harness.py \
  --manifest integrations/prepomax-codeaster/harness/codeaster.example.json \
  --preflight-only
```

Execute the study:

```bash
python integrations/prepomax-codeaster/harness/astermax_harness.py \
  --manifest path/to/case.harness.json
```

Run the internal harness contract test without invoking any FEA solver:

```bash
python integrations/prepomax-codeaster/harness/astermax_harness.py --self-test
```

## Manifest contract

Important properties:

| Property | Meaning |
|---|---|
| `schema` | Harness manifest version. Current value: `1`. |
| `case_name` | Human-readable regression/smoke-case name. |
| `solver` | `code_aster` or `calculix`. |
| `job_name` | Solver job basename. |
| `working_directory` | Directory containing the generated solver study. |
| `solver_executable` | `as_run`, `ccx`, or an explicit executable path. |
| `timeout_seconds` | Hard process timeout. |
| `required_inputs` | Files that must exist before execution. |
| `required_outputs` | Solver-owned files that are cleared before execution and required afterward. |
| `environment` | Optional solver-specific environment variables. |
| `result_contract` | Code_Aster interoperability-table requirements. |

Environment variables and `~` are expanded in manifest string values.

## Run report

Every invocation writes `<job>.harness.json` in the study directory unless `--report` overrides it. The report records:

- UTC start/finish timestamps;
- host/Python information;
- exact command executed;
- timeout and exit code;
- stdout/stderr log paths;
- every preflight and post-run check;
- SHA-256, size and modification timestamp of study inputs and solver outputs;
- stale outputs removed before execution;
- final `PASS`, `FAIL` or `PRECHECK_ONLY` state.

Stdout and stderr are retained under `.astermax-harness/` in the case working directory.

## Code_Aster result contract

The current PrePoMax bridge reads these deterministic `IMPR_TABLE` sections from `<job>.resu`:

- `PPM_DEPL`
- `PPM_STRESS_N`
- `PPM_STRESS_S`
- `PPM_STRAIN_N`
- `PPM_STRAIN_S`

The harness checks the same contract before the GUI receives the result. RMED remains the complete Code_Aster result database; `.resu` is the deterministic interoperability channel for the existing `CaeResults` path.

## Extension points

The manifest and report formats are solver-neutral. The next adapters can add solver profiles without changing GUI analysis logic. Future useful contracts include numerical regression tolerances, mesh-count fingerprints, reaction-force balance, energy checks and reference-solution comparisons. Those checks should compare real solver output against explicit reference data; they should never invent fallback values.
