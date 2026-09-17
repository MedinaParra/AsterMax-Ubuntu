param([string]$Dist)
$ErrorActionPreference='Stop'

$root=Join-Path $Dist 'Validation\C10.10.1-Native-Windows'
New-Item -ItemType Directory -Force $root | Out-Null
$root=(Resolve-Path $root).Path
$runner=(Resolve-Path (Join-Path $Dist 'AsterMaxRuntime\CodeAster\astermax-codeaster-runner.cmd')).Path

function Test-NativeProbe {
    Write-Host 'NATIVE_STAGE: probe native runner'
    $probe=& $runner probe
    $exit=$LASTEXITCODE
    $probe | Set-Content (Join-Path $root 'native-probe.json') -Encoding UTF8
    if($exit -ne 0){ return $false }
    try { $ready=$probe | ConvertFrom-Json } catch { return $false }
    return ($ready.ready -and $ready.transport -eq 'WINDOWS_NATIVE' -and $ready.wsl_required -ne $true)
}

$nativeReady=Test-NativeProbe
if(-not $nativeReady) {
    $msi=Join-Path $env:RUNNER_TEMP 'code-aster-v2025.msi'
    $validMsi=(Test-Path $msi) -and ((Get-FileHash $msi -Algorithm MD5).Hash -eq '95A2171A6EB967874F7D0C98E881C66C')
    if(-not $validMsi) {
        Write-Host 'NATIVE_STAGE: download provider MSI with resumable retries'
        if(Test-Path $msi){ Remove-Item $msi -Force }
        for($attempt=1;$attempt -le 3;$attempt++) {
            & curl.exe -L --fail --silent --show-error --continue-at - --connect-timeout 30 --max-time 900 --output $msi 'https://simulease.com/wp-content/uploads/2026/03/code-aster_v2025_std.msi'
            if($LASTEXITCODE -eq 0 -and (Test-Path $msi)){ break }
            if($LASTEXITCODE -eq 33 -and (Test-Path $msi)){ Remove-Item $msi -Force }
            if($attempt -eq 3){ throw 'Provider MSI download failed after three attempts' }
            Write-Host "NATIVE_STAGE: retry MSI download, attempt $($attempt+1)"
        }
    } else { Write-Host 'NATIVE_STAGE: reuse verified provider MSI' }
    if ((Get-FileHash $msi -Algorithm MD5).Hash -ne '95A2171A6EB967874F7D0C98E881C66C') {throw 'Provider MSI fingerprint mismatch'}

    Write-Host 'NATIVE_STAGE: install provider MSI'
    $installLog=Join-Path $env:RUNNER_TEMP 'aster-install.log'
    $p=Start-Process msiexec.exe -ArgumentList @('/i',('"'+$msi+'"'),'/qn','/norestart','/l*v',('"'+$installLog+'"')) -PassThru
    if(-not $p.WaitForExit(600000)){
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        throw 'Provider installation timed out; see aster-install.log'
    }
    if($p.ExitCode -notin @(0,3010)){throw "Code_Aster MSI failed: $($p.ExitCode)"}

    $nativeReady=Test-NativeProbe
    if(-not $nativeReady){ throw 'Native probe failed after genuine Windows Code_Aster installation.' }
}

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

@{
    release='C10.10.1'
    transport='WINDOWS_NATIVE'
    provider_msi_md5='95a2171a6eb967874f7d0c98e881c66c'
    solver_execution='RUN'
    synthetic_results_allowed=$false
    wsl_required=$false
} | ConvertTo-Json | Set-Content (Join-Path $root 'WINDOWS_NATIVE_EVIDENCE.json')

Write-Host 'NATIVE_STAGE: reject invalid MED fields'
& $python native-windows/test-c1011-med-field-discovery.py native-windows/bridge-c964-med-results.py (Join-Path $root 'astermax-tet4-bar.rmed') (Join-Path $root 'MED_FIELD_REJECTION_TESTS.json')
if($LASTEXITCODE -ne 0){throw 'MED field ambiguity regression failed'}
