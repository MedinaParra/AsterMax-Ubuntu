# AsterMax C12.08 RC2: Windows runner file-lock correction

The Code_Aster adapter must not copy files owned by its parent application.
`Copy-Workspace` now excludes the two live parent stdout/stderr logs, the live
solve-state JSON and its atomic temporary files in both directions. It preserves
all actual solver inputs, results and diagnostics, and still fails on unrelated
copy or source-enumeration errors.

## Exact application source

The native Windows workflow checks out PrePoMax commit
`3669e65581650e5d9d868aa761db9efd856f8571`, applies the committed source overlay,
and verifies all 1,198 normalized source files against `source-manifest.json`.
This reproduces the corresponding application source shipped in the November 3
C12.08 RC1 package, including the parser, MAIL format, progress, strict-chain and
live-console corrections. Four byte-identical Linux filename aliases are
normalized for Windows. No previous application EXE, DLL, bin or obj is reused.

The source overlay contains 65 added/changed files. It is an explicit snapshot,
not a replay of the older patch chain on main. The manifest documents its SHA256
and the hash of every reconstructed source file. The source and resulting
application retain the upstream license in `source/LICENSE` and in the artifact.

## Validation

The Actions run reproduces the old sharing conflict and tests the correction on
Windows PowerShell 5.1 and PowerShell 7. A separate full-runner test exercises
success, large stdout/stderr, fatal output despite exit 0, nonzero exit, and
missing result output with an explicitly synthetic backend.

All nine application projects are rebuilt natively using Visual Studio MSBuild
in Release x64, followed by gates against the actual resulting Windows binaries
for contact laws, topology, bonded MPC, the strict fixture and embedded resources.
The generated artifact records its exact GitHub commit and product hashes.

The workflow does not claim real Code_Aster execution, an interactive GUI test,
or a successful solve of a user's engineering model. It does not contain user
PMX, CAD or other private project inputs. Its application-update artifact must be
combined with the existing runtime package; it is not a new solver installation.
