# C10.78 BREP runtime repair

2026-10-15. Main untouched.

- User screenshot: Importing brep file failed; title C10.41 RC1.
- Corrected import uses unique VIS files, invariant numeric CLI arguments, executable/input/output checks, and actionable NetGen status/exit code messages. Title updated to C10.78.
- Windows build PASS on c216c04d499325fe17f8d5fdc05fd1d4e9a6ca77, but real NetGen 3.0 RC1 fixture visualization FAIL: exit -1073741819 (0xC0000005), after stdout reported successful BREP loading and one solid. Run 38790634322. No claim that the user's exact failure has the same cause.
- Switched packaged native mesher to official PrePoMax v1.4.0 runtime previously used by the pinned-source workflows; no change to FEM solver.
- Run 38791446997 at 1b76c9714fd70aa8fcfd2e482edbc0dd433c4d75: Windows x64 build PASS; real native B01-100x10x10 BREP visualization PASS, exit 0, VIS 2393 bytes; packaging PASS.
- ZIP artifact 11999343913, AsterMax-C10.78-BREP-repair-Windows-x64.
- Exact incident STEP: BLOCKED_NOT_PROVIDED. Full GUI import, VIS parser acceptance, STEP conversion, meshing, Code_Aster solve and performance: NOT_RUN. Native fixture test covers BREP-to-VIS only.
