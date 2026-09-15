param([string]$Dist)
$ErrorActionPreference='Stop'
$msi=Join-Path $env:RUNNER_TEMP 'code-aster-v2025.msi'
Write-Host 'NATIVE_STAGE: download provider MSI'
Invoke-WebRequest 'https://simulease.com/wp-content/uploads/2026/03/code-aster_v2025_std.msi' -OutFile $msi -TimeoutSec 180
if ((Get-FileHash $msi -Algorithm MD5).Hash -ne '95A2171A6EB967874F7D0C98E881C66C') {throw 'Provider MSI fingerprint mismatch'}
Write-Host 'NATIVE_STAGE: install provider MSI'
$p=Start-Process msiexec.exe -ArgumentList @('/i',('"'+$msi+'"'),'/qn','/norestart','/l*v',('"'+(Join-Path $env:RUNNER_TEMP 'aster-install.log')+'"')) -PassThru
if(-not $p.WaitForExit(240000)){Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue;throw 'Provider installation timed out; see aster-install.log'}
if($p.ExitCode -notin @(0,3010)){throw "Code_Aster MSI failed: $($p.ExitCode)"}
$root=Join-Path $Dist 'Validation\C10.11-Native-Windows'
New-Item -ItemType Directory -Force $root | Out-Null
$root=(Resolve-Path $root).Path
$runner=(Resolve-Path (Join-Path $Dist 'AsterMaxRuntime\CodeAster\astermax-codeaster-runner.cmd')).Path
Write-Host 'NATIVE_STAGE: probe native runner'
$probe=& $runner probe
$probe | Set-Content (Join-Path $root 'native-probe.json') -Encoding UTF8
if($LASTEXITCODE -ne 0){throw "Native probe failed: $probe"}
$ready=$probe | ConvertFrom-Json
if(-not $ready.ready -or $ready.transport -ne 'WINDOWS_NATIVE'){throw 'Expected real Windows native backend, not WSL'}
python native-windows/c1008-real-tetra/generate_tetra_bar.py --out $root --name astermax-tet4-bar
if($LASTEXITCODE -ne 0){throw 'Fixture generation failed'}
Write-Host 'NATIVE_STAGE: solve real tetra model'
& $runner (Join-Path $root 'astermax-tet4-bar.export') $root | Tee-Object (Join-Path $root 'NATIVE_SOLVER_STDOUT.log')
if($LASTEXITCODE -ne 0){throw 'Native Windows solve failed'}
$env:ASTERMAX_MED_BRIDGE_MODE='production'
$python=(Resolve-Path (Join-Path $Dist 'AsterMaxRuntime\Python\python.exe')).Path
Write-Host 'NATIVE_STAGE: import genuine MED'
& $python native-windows/bridge-c964-med-results.py (Join-Path $root 'astermax-tet4-bar.rmed') (Join-Path $root 'astermax-tet4-bar.astermax-results.json') (Join-Path $root 'astermax-tet4-bar.astermax-results.vtu')
if($LASTEXITCODE -ne 0){throw 'Native Windows MED handoff failed'}
& $python native-windows/c1008-real-tetra/validate_c1008.py --root $root --name astermax-tet4-bar
if($LASTEXITCODE -ne 0){throw 'Native Windows numerical validation failed'}
@{transport='WINDOWS_NATIVE';provider_msi_md5='95a2171a6eb967874f7d0c98e881c66c';solver_execution='RUN';synthetic_results_allowed=$false} | ConvertTo-Json | Set-Content (Join-Path $root 'WINDOWS_NATIVE_EVIDENCE.json')

Write-Host 'NATIVE_STAGE: reject invalid MED fields'
& $python native-windows/test-c1011-med-field-discovery.py native-windows/bridge-c964-med-results.py (Join-Path $root 'astermax-tet4-bar.rmed') (Join-Path $root 'MED_FIELD_REJECTION_TESTS.json')
if($LASTEXITCODE -ne 0){throw 'MED field ambiguity regression failed'}
