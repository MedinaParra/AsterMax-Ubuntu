# AsterMax Mechanical C12.08 RC2

**Open-source mechanical CAE / FEA workflow for Windows x64 with native Code_Aster integration.**

AsterMax Mechanical is an engineering pre/post-processing environment derived from the GPLv3 PrePoMax ecosystem. Its goal is an efficient, integrated mechanical-engineering workflow with an independent AsterMax user experience: geometry, materials, interactions, meshing, constraints, loads, solving, verification and result review from a single desktop environment.

> **Current version on main:** C12.08 RC2, with the Windows runner file-lock correction. Native build and regression checks passed. Real Code_Aster execution and interactive GUI validation were not run for this RC2.

## RC2 status and provenance

**Application/source baseline:** [53949bb581ea61b274495143a2cd6293fa9def22](https://github.com/MedinaParra/AsterMax-Ubuntu/commit/53949bb581ea61b274495143a2cd6293fa9def22), integrated into `main` on 2026-11-04.

**Windows build and regression evidence:** [GitHub Actions run 41828938627](https://github.com/MedinaParra/AsterMax-Ubuntu/actions/runs/41828938627), completed successfully on 2026-11-04 for that exact commit.

| RC2 check | Status |
|---|---|
| Exact reconstruction and hash verification of 1,198 application source files | PASS |
| Clean native Windows Release x64 build of all nine projects | PASS |
| Reproduction of the original runner file-lock failure | PASS |
| Workspace ownership and copy-back regressions on Windows PowerShell 5.1 / PowerShell 7 | PASS |
| Full runner success/failure handling with a synthetic native process | PASS, synthetic backend only |
| Contact-law, topology, bonded MPC, strict-fixture and resource gates against the Windows application binaries | PASS |
| Real Code_Aster execution for this RC2 | NOT_RUN |
| Interactive GUI validation for this RC2 | NOT_RUN |
| Solve of a user's engineering model | NOT_RUN |

The correction prevents the Code_Aster adapter from copying live stdout/stderr logs, solve-state JSON and atomic temporary files owned by the parent application. Actual solver inputs, results and diagnostics remain part of the workspace transfer, and unrelated copy failures still fail the run.

The RC2 build reconstructs the application source shipped in the November 3 C12.08 RC1 package from a pinned PrePoMax commit and a hash-checked source overlay. It does not reuse previous application EXE, DLL, bin or obj outputs. See [the RC2 source, build and validation notes](native-windows/c1208-rc2/README.md).

These checks establish the declared build and regression results only. This release candidate is not a claim of universal FEA certification. Each engineering model still requires appropriate verification, benchmark comparison, mesh/convergence review, material-model validation and applicable design-code checks.

## RC2 build artifacts

The verified workflow generated:

- [AsterMax-C1208-RC2-Windows-x64-53949bb581ea61b274495143a2cd6293fa9def22](https://github.com/MedinaParra/AsterMax-Ubuntu/actions/runs/41828938627/artifacts/13321686704)
- [AsterMax-C1208-RC2-Audit-53949bb581ea61b274495143a2cd6293fa9def22](https://github.com/MedinaParra/AsterMax-Ubuntu/actions/runs/41828938627/artifacts/13321132256)

The application-update artifact must be combined with the existing runtime package. It is not a complete portable solver installation. It contains no private PMX, CAD or other user project inputs. GitHub Actions artifacts are subject to the workflow's 14-day retention period; the committed source and build instructions remain available after artifact expiry.

## Historical C10.41 RC1 qualification

The earlier C10.41 RC1 baseline is commit [9b823e943ffafa3b94de428ff5375feb625939e6](https://github.com/MedinaParra/AsterMax-Ubuntu/commit/9b823e943ffafa3b94de428ff5375feb625939e6), with [qualification run 37651647328](https://github.com/MedinaParra/AsterMax-Ubuntu/actions/runs/37651647328) completed successfully on 2026-10-07.

That historical workflow covered the Windows build, native Code_Aster, compiled exporter, a real contact deck, STEP/contact/gravity regression, native GUI conformance and save/close/reopen. Its end-to-end results apply to the C10.41 baseline and must not be presented as a new end-to-end qualification of C12.08 RC2.

## Integrated product direction

The current RC2 is a CAE application. The longer-term AsterMax direction is an integrated mechanical-engineering environment with two connected workflows.

### Design

A parametric mechanical-CAD workflow based on original AsterMax implementation and lawfully licensed components:

`Part / Sketch → Features → Assemblies → Drawings / Exchange`

The goal is to preserve interaction patterns that experienced mechanical designers find efficient—feature history, constrained sketches, direct access to common operations and predictable assemblies—without copying proprietary source code, artwork, icons or distinctive trade dress.

### Analysis

A structured mechanical-analysis workflow:

`Geometry → Materials → Interactions → Mesh → Constraints / Loads → Solve → Results → Verification`

The goal is to keep model definition and result interpretation predictable for experienced FEA users while using AsterMax code, Code_Aster and other legally cleared components.

See `docs/ARCHITECTURE_IP_BOUNDARIES.md` for the intended technical and licensing boundaries.

## Main engineering direction

AsterMax development currently emphasizes:

- STEP-based mechanical assemblies;
- a clear engineering model hierarchy;
- structural static workflows;
- automatic/default material assignment where appropriate;
- contact-oriented modelling;
- gravity and mechanical loading;
- native Code_Aster solving on Windows;
- displacement, stress and reaction result review;
- project persistence and reproducibility;
- validation evidence instead of silent success;
- explicit PASS / FAIL / BLOCKED / NOT_RUN qualification logic.

## Development policy

`main` contains the C12.08 RC2 source snapshot, Windows runner-lock correction and reproducible build/validation workflow, alongside the historical patch chain and project policies.

Keep the historical C10.41 RC1 qualification evidence separate from RC2 evidence. New functionality and behavior changes belong in development branches. Record checks against the exact candidate commit and complete the required real-solver and GUI qualification before claiming a new end-to-end validated release.

## Repository note

The repository name `AsterMax-Ubuntu` is historical. The current RC2 build and the historical C10.41 RC1 qualification described here focus on the **native Windows x64** path with **Code_Aster for Windows**.

Legacy Linux/Ubuntu work remains part of the project history. Keep its evidence distinct from the Windows release baselines.

## Independence, provenance and licensing

AsterMax is an independent project and is not affiliated with or endorsed by proprietary CAD/CAE vendors used for external engineering comparison.

AsterMax must not redistribute proprietary source code, binaries, logos, icons, screenshots, documentation, tutorial assets or distinctive trade dress without an express right to do so. Familiar workflows may be used as functional requirements, but implementation and AsterMax visual identity must remain independent.

Because the existing native application is historically derived from PrePoMax, GPLv3 obligations are treated as the conservative baseline for derivative code when it is conveyed. Upstream components retain their respective copyright and license terms.

Development and release rules are documented in:

- `LICENSE`
- `NOTICE.md`
- `IP_POLICY.md`
- `THIRD_PARTY_NOTICES.md`
- `CONTRIBUTING.md`
- `TRADEMARKS.md`
- `docs/COMMERCIAL_RELEASE_CHECKLIST.md`

## Qualification boundary

A successful automated workflow means that the tested software chain completed the declared qualification contract for the tested model and environment. It does **not** mean that every element formulation, contact condition, nonlinear model, material law, geometry or engineering use case has been independently validated.

For production engineering decisions, always preserve model inputs, solver version, mesh information, boundary conditions, result files and verification evidence.

---

**AsterMax Mechanical C12.08 RC2**

Windows x64 · Native build and regression checks PASS · Real solver / interactive GUI validation NOT_RUN for RC2
