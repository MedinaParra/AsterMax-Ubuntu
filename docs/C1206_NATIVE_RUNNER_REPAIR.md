# C12.06: native Code_Aster setup and Windows package repair

## Reported failure

The Windows application stopped at Solve with:

`Code_Aster runner is not configured. Set ASTERMAX_CODE_ASTER_RUNNER to a validated runner executable/script.`

The C10.86 application archive omitted the adapter expected at
`AsterMaxRuntime/CodeAster/astermax-codeaster-runner.cmd`. Later packaging
used a different directory, and the C11.99 distribution gate searched for
`PrePoMax.exe` although the build produces `AsterMax Mechanical.exe`.
The screenshot's C10.41 RC1 title was inherited branding, not a reliable
identifier of the downloaded archive.

## Repair

- Package the complete native adapter in its expected directory.
- Package Python with numpy/h5py and all three tools used by the generated
  solve transaction: MED bridge, model-fingerprint binder, and mechanical
  qualification.
- Require both adapter files during discovery, support the previously used
  `CodeAster/` directory, and replace the environment-variable error with
  actionable Spanish instructions.
- Add **Solucion > Instalar motor**. This launches the packaged setup without
  blocking the application. **Verificar** retains the installation-folder
  selector for an existing native installation.
- Download the original Windows MSI directly from its provider, verify its
  pinned size and SHA-256, run Windows Installer, and require a successful
  native probe before reporting setup success. No persistent environment
  variables are required or modified.
- Strengthen the probe to require Code_Aster identity, normal completion,
  a new nonempty `.mess`, and rejection of fatal/internal nonzero status.
- Identify the application as C12.06 and publish the ZIP only after Windows
  compilation and genuine TETRA4/MED numerical validation succeed.

## Use

1. Extract the entire ZIP into a new directory.
2. Open `AsterMax Mechanical.exe`.
3. If Code_Aster is not installed, choose **Solucion > Instalar motor**.
   The first setup downloads approximately 398 MB and may require a Windows
   permission prompt. `Configurar-Code_Aster.cmd` offers the same setup.
4. When setup completes, use **Verificar** and then **Resolver**.

Setup first checks a valid existing installation, so it does not reinstall
a working motor. It preserves installation diagnostics under
`%LOCALAPPDATA%/AsterMax/Logs/CodeAsterSetup` by default. It does not report
success merely because the MSI finished. A failing existing engine requires
diagnosis rather than an automatic reinstall.

## Validation boundaries

Discovery tests execute the C# helper extracted from the generated source.
Probe contract fixtures and process stubs are explicitly labelled as contract
tests, not solver evidence. CI separately executes the original native solver,
checks numerical TETRA4 results, and reads the real MED using the packaged
Python and bridge. The historical numerical test is invoked with
`-RequireInstalledRuntime`, preventing a hidden installation fallback from
masking a setup failure.

CI records statuses and the exact commit in `ASTERMAX_BUILD_MANIFEST.json`,
with SHA-256 checks of the executable and every package entry. Interactive GUI
operation and the user's model are not claimed validated by the TETRA4 test.

## Runtime provenance

The Code_Aster provider MSI is not redistributed in this ZIP. The bootstrap
downloads `code-aster_v2025_std.msi` from SimulEase, with the same pinned
398012592-byte payload and SHA-256 already used by the repository's native
Windows integration. The MSI performs the provider's required installation
steps; its contents are not presented as a portable engine.

- Provider: https://simulease.com/
- Port licensing/source information: https://code-aster-windows.com/faq/
- AsterMax source and build recipe: https://github.com/MedinaParra/AsterMax-Ubuntu
- PrePoMax source base: https://github.com/tsvilans/PrePoMax/tree/3669e65581650e5d9d868aa761db9efd856f8571

No alternate solver or synthetic FEA results are introduced.
