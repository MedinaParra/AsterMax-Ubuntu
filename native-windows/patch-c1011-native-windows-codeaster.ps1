param([string]$Root)
$ErrorActionPreference='Stop'

# C10.11 — native Windows Code_Aster bridge.
# The packaged AsterMax runner no longer uses WSL. The C# preflight keeps fail-closed
# semantics and allows enough time for a real Windows Code_Aster smoke solve.

$solvePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
if(!(Test-Path $solvePath)){ throw 'C10.11 requires the C10.05+ native solve transaction.' }
$s=Get-Content $solvePath -Raw

if($s.Contains('process.WaitForExit(15000)')){
    $s=$s.Replace('process.WaitForExit(15000)','process.WaitForExit(120000)')
}
if($s.Contains('Runner probe timed out after 15 seconds.')){
    $s=$s.Replace('Runner probe timed out after 15 seconds.','Native Windows Code_Aster probe timed out after 120 seconds.')
}
if($s.Contains('ASTERMAX_C1005_REAL_BACKEND_PROBE_V1')){
    $s=$s.Replace('ASTERMAX_C1005_REAL_BACKEND_PROBE_V1','ASTERMAX_C1011_WINDOWS_NATIVE_CODE_ASTER_V1')
}

$transportAnchor='                ["code_aster_runner_source"]=String.IsNullOrWhiteSpace(runner)?"missing":(runner.IndexOf("AsterMaxRuntime",StringComparison.OrdinalIgnoreCase)>=0?"packaged":"environment"),'
if($s.Contains($transportAnchor) -and -not $s.Contains('["code_aster_transport"]="WINDOWS_NATIVE"')){
    $s=$s.Replace($transportAnchor,$transportAnchor+[Environment]::NewLine+'                ["code_aster_transport"]="WINDOWS_NATIVE",'+[Environment]::NewLine+'                ["wsl_required"]=false,')
}

Set-Content $solvePath $s -Encoding UTF8

$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(!(Test-Path $uiPath)){ throw 'C10.11 native UI source missing.' }
$u=Get-Content $uiPath -Raw
$u=$u.Replace('Code_Aster | WSL verified solve','Code_Aster | Windows native solve')
$u=$u.Replace('Code_Aster | native solve','Code_Aster | Windows native solve')
Set-Content $uiPath $u -Encoding UTF8

Write-Host 'C10.11 native Windows Code_Aster preflight injected; WSL is not required.' -ForegroundColor Green
