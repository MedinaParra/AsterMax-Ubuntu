# AsterMax Mechanical C9.75 — Windows x64

Extract the whole ZIP to a new writable folder. Run AsterMax Mechanical.exe with lib and NetGen beside it. Requires .NET Framework 4.8.

Changes: preserve ModelTree lookup identifiers, wire Materials / Solid Section / Analysis Step / Supports / Loads to native handlers, include the CAD mesher, initialize a writable CAD work directory, and log initialization errors.

See C9.75_VALIDATION.json and ASTERMAX_RUNTIME_STEP.json for the actual Windows test outcome. The runtime test imports a STEP solid and generates a real NetGen volume mesh. AsterMax-C9.75.png is captured from that execution when available. These are CAD/mesh tests, not an FEA solve.

Code_Aster solve and result reimport are not integrated in this build. No FEA accuracy or full PMV claim is made. No CalculiX solver is bundled.

Source and reproducible build: https://github.com/MedinaParra/AsterMax-Ubuntu/tree/codex/c975-native-startup-repair
Upstream source: https://github.com/tsvilans/PrePoMax/tree/3669e65581650e5d9d868aa761db9efd856f8571
The native application is derived from GPL-3.0 PrePoMax. Upstream and third-party licenses continue to apply.
