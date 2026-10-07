param([string]$Dist)
$ErrorActionPreference='Stop'

$root=Join-Path $Dist 'Validation\C10.10.1-Native-Windows'
New-Item -ItemType Directory -Force $root | Out-Null
$root=(Resolve-Path $root).Path
$runner=(Resolve-Path (Join-Path $Dist 'AsterMaxRuntime\CodeAster\astermax-codeaster-runner.cmd')).Path
$providerMsiUrl='https://simulease.com/wp-content/uploads/2026/03/code-aster_v2025_std.msi'
$providerMsiSha256='B789FEFFC12E0FECBCFBABE6D386FA15C1AB74797C8C9D27A5733F8D2B5D092D'
$providerMsiSize=398012592

function Test-NativeProbe {
    Write-Host 'NATIVE_STAGE: probe native runner'
    $probe=& $runner probe
    $exit=$LASTEXITCODE
    $probe | Set-Content (Join-Path $root 'native-probe.json') -Encoding UTF8
    if($exit -ne 0){ return $false }
    try { $ready=$probe | ConvertFrom-Json } catch { return $false }
    return ($ready.ready -and $ready.transport -eq 'WINDOWS_NATIVE' -and $ready.wsl_required -ne $true)
}

function Get-FileLengthOrZero([string]$Path) {
    if(Test-Path $Path){ return [int64](Get-Item $Path).Length }
    return [int64]0
}

function Invoke-ResumableProviderDownload {
    param(
        [string]$Url,
        [string]$Destination,
        [int64]$ExpectedSize,
        [int]$MaxAttempts=8
    )

    for($attempt=1; $attempt -le $MaxAttempts; $attempt++) {
        $offset=Get-FileLengthOrZero $Destination
        if($offset -gt $ExpectedSize) {
            Write-Warning "Provider MSI partial file is larger than expected ($offset > $ExpectedSize); restarting from zero."
            Remove-Item $Destination -Force
            $offset=0
        }
        if($offset -eq $ExpectedSize) {
            Write-Host "ASTER_MSI_DOWNLOAD_COMPLETE bytes=$offset attempt=$attempt"
            return
        }

        Write-Host "ASTER_MSI_DOWNLOAD_ATTEMPT=$attempt OFFSET=$offset EXPECTED=$ExpectedSize"
        $curlArgs=@(
            '-L','--fail','--retry','2','--retry-all-errors','--retry-delay','3',
            '--connect-timeout','30','--speed-time','60','--speed-limit','1024'
        )
        if($offset -gt 0) {
            $curlArgs += @('--continue-at',[string]$offset)
        }
        $curlArgs += @('--output',$Destination,$Url)

        & curl.exe @curlArgs
        $curlExit=$LASTEXITCODE
        $current=Get-FileLengthOrZero $Destination
        Write-Host "ASTER_MSI_DOWNLOAD_RESULT attempt=$attempt exit=$curlExit bytes=$current"

        if($curlExit -eq 0 -and $current -eq $ExpectedSize) { return }

        # curl 33 means the provider refused the requested byte range. Restart once from
        # zero rather than repeatedly appending or accepting a corrupt provider payload.
        if($curlExit -eq 33 -and $current -gt 0) {
            Write-Warning 'Provider does not support the requested resume range; restarting the MSI download from zero.'
            Remove-Item $Destination -Force
        }
        elseif($current -gt $ExpectedSize) {
            Write-Warning 'Provider MSI download exceeded the pinned size; deleting the partial payload before retry.'
            Remove-Item $Destination -Force
        }

        if($attempt -lt $MaxAttempts) { Start-Sleep -Seconds ([Math]::Min(20,3*$attempt)) }
    }

    $finalBytes=Get-FileLengthOrZero $Destination
    throw "Provider MSI download failed after $MaxAttempts attempts; received $finalBytes of $ExpectedSize bytes."
}

$nativeReady=Test-NativeProbe
if(-not $nativeReady) {
    $msi=Join-Path $env:RUNNER_TEMP 'code-aster-v2025.msi'
    Write-Host 'NATIVE_STAGE: download provider MSI'
    if(Test-Path $msi){ Remove-Item $msi -Force }
    Invoke-ResumableProviderDownload -Url $providerMsiUrl -Destination $msi -ExpectedSize $providerMsiSize
    if(-not(Test-Path $msi)){ throw 'Provider MSI download failed' }
    $actualSize=(Get-Item $msi).Length
    $actualSha256=(Get-FileHash $msi -Algorithm SHA256).Hash.ToUpperInvariant()
    Write-Host "ASTER_MSI_SIZE=$actualSize"
    Write-Host "ASTER_MSI_SHA256=$actualSha256"
    if($actualSize -ne $providerMsiSize){ throw "Provider MSI size mismatch: expected $providerMsiSize, got $actualSize" }
    if($actualSha256 -ne $providerMsiSha256){ throw "Provider MSI SHA-256 mismatch: expected $providerMsiSha256, got $actualSha256" }

    Write-Host 'NATIVE_STAGE: install provider MSI'
    $installLog=Join-Path $env:RUNNER_TEMP 'aster-install.log'
    $p=Start-Process msiexec.exe -ArgumentList @('/i',('"'+$msi+'"'),'/qn','/norestart','/l*v',('"'+$installLog+'"')) -PassThru
    if(-not $p.WaitForExit(600000)){
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        if(Test-Path $installLog){ Copy-Item $installLog (Join-Path $root 'aster-install.log') -Force }
        throw 'Provider installation timed out; see aster-install.log'
    }
    if(Test-Path $installLog){ Copy-Item $installLog (Join-Path $root 'aster-install.log') -Force }
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
    provider_msi_sha256=$providerMsiSha256.ToLowerInvariant()
    provider_msi_size=$providerMsiSize
    provider_msi_origin=$providerMsiUrl
    provider_msi_observed_date='2026-09-16'
    solver_execution='RUN'
    synthetic_results_allowed=$false
    wsl_required=$false
} | ConvertTo-Json | Set-Content (Join-Path $root 'WINDOWS_NATIVE_EVIDENCE.json')

Write-Host 'NATIVE_STAGE: reject invalid MED fields'
& $python native-windows/test-c1011-med-field-discovery.py native-windows/bridge-c964-med-results.py (Join-Path $root 'astermax-tet4-bar.rmed') (Join-Path $root 'MED_FIELD_REJECTION_TESTS.json')
if($LASTEXITCODE -ne 0){throw 'MED field ambiguity regression failed'}
