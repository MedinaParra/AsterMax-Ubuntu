#!/usr/bin/env python3
"""Static regression guard for native Code_Aster completion admission."""
from pathlib import Path

ROOT=Path(__file__).resolve().parent
runner=(ROOT/"runtime"/"CodeAster"/"astermax-codeaster-runner.ps1").read_text(encoding="utf-8-sig")
required=[
    "function Test-CodeAsterNormalTermination",
    r"ARRET\s+NORMAL",
    "MessNormalTermination",
    "solver_probe_normal_termination",
    "refusing to publish solver outputs",
]
for token in required:
    assert token in runner, token
normal_check=runner.index("if (-not (Test-CodeAsterNormalTermination $expectedOutputs['mess']))")
publish=runner.index("Copy-Workspace $stage $resolvedWorkspace", normal_check)
assert normal_check < publish
assert 'Fail "Native solver .mess does not attest ARRET NORMAL; refusing to publish solver outputs." 31' in runner
print("CODE_ASTER_RUNNER_COMPLETION_GATE_OK")
