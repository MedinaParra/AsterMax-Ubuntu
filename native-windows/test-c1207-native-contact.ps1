param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$Dist,
    [string]$OutDir,
    [switch]$PrepareOnly
)
$ErrorActionPreference='Stop'
if($env:OS -ne 'Windows_NT'){ throw 'This admission test requires genuine native Windows Code_Aster.' }
$Root=(Resolve-Path -LiteralPath $Root).Path
$Dist=(Resolve-Path -LiteralPath $Dist).Path
if([string]::IsNullOrWhiteSpace($OutDir)){ $OutDir=Join-Path $Dist 'Validation/C12.07-Native-Contact' }
if(Test-Path -LiteralPath $OutDir){
    if(@(Get-ChildItem -LiteralPath $OutDir -Force).Count -gt 0){ throw 'Contact validation requires a fresh output directory.' }
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir=(Resolve-Path -LiteralPath $OutDir).Path
$python=Join-Path $Dist 'AsterMaxRuntime/Python/python.exe'
$runner=Join-Path $Dist 'AsterMaxRuntime/CodeAster/astermax-codeaster-runner.ps1'
$bridge=Join-Path $Dist 'AsterMaxTools/bridge-c964-med-results.py'
$powershell=Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$scripts=Join-Path $PSScriptRoot 'c1207-contact'
foreach($file in @($python,$runner,$bridge,$powershell)){
    if(-not (Test-Path -LiteralPath $file -PathType Leaf)){ throw "Native contact prerequisite missing: $file" }
}

function Quote-ProcessArgument([string]$Value) {
    if($Value -match '["\r\n]'){ throw 'Unexpected quote or newline in benchmark process argument.' }
    return '"'+($Value -replace '(\\+)$','$1$1')+'"'
}

function Invoke-BenchmarkProcess([string]$Program,[string[]]$Arguments,[string]$Directory,[string]$LogPrefix,[int]$TimeoutSeconds=900) {
    $process=New-Object System.Diagnostics.Process
    $process.StartInfo=New-Object System.Diagnostics.ProcessStartInfo
    $process.StartInfo.FileName=$Program
    $process.StartInfo.Arguments=(@($Arguments | ForEach-Object { Quote-ProcessArgument $_ }) -join ' ')
    $process.StartInfo.WorkingDirectory=$Directory
    $process.StartInfo.UseShellExecute=$false
    $process.StartInfo.CreateNoWindow=$true
    $process.StartInfo.RedirectStandardOutput=$true
    $process.StartInfo.RedirectStandardError=$true
    $process.StartInfo.StandardOutputEncoding=New-Object Text.UTF8Encoding($false)
    $process.StartInfo.StandardErrorEncoding=New-Object Text.UTF8Encoding($false)
    $process.StartInfo.EnvironmentVariables['PYTHONUTF8']='1'
    $process.StartInfo.EnvironmentVariables['PYTHONIOENCODING']='utf-8'
    if([IO.Path]::GetFileName($Program) -ieq 'powershell.exe'){
        # Process.Start bypasses pwsh's Windows PowerShell module-path adjustment.
        # Let the child rebuild its defaults without changing the parent environment.
        $process.StartInfo.EnvironmentVariables.Remove('PSModulePath')
    }
    try {
        if(-not $process.Start()){ throw "Unable to start $Program" }
        $stdout=$process.StandardOutput.ReadToEndAsync()
        $stderr=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit($TimeoutSeconds*1000)){
            & "$env:SystemRoot/System32/taskkill.exe" /PID $process.Id /T /F | Out-Null
            throw "Contact benchmark process timed out: $Program"
        }
        $result=[pscustomobject]@{ExitCode=$process.ExitCode;Stdout=$stdout.Result;Stderr=$stderr.Result}
        [IO.File]::WriteAllText($LogPrefix+'.stdout.log',$result.Stdout,(New-Object Text.UTF8Encoding($false)))
        [IO.File]::WriteAllText($LogPrefix+'.stderr.log',$result.Stderr,(New-Object Text.UTF8Encoding($false)))
        return $result
    }
    finally { $process.Dispose() }
}

function Require-Success([object]$Result,[string]$Stage) {
    if($Result.ExitCode -ne 0){
        $details=$Result.Stdout+[Environment]::NewLine+$Result.Stderr
        if($details.Length -gt 5000){ $details=$details.Substring($details.Length-5000) }
        throw "$Stage failed (exit $($Result.ExitCode)): $details"
    }
}

Write-Host 'CONTACT_STAGE: generate three-body model with twelve overlapping slave nodes'
$generated=Invoke-BenchmarkProcess $python @((Join-Path $scripts 'generate_contact_fixture.py'),'--out',$OutDir) $OutDir (Join-Path $OutDir 'generate') 60
Require-Success $generated 'Contact fixture generation'
$corrected=Join-Path $OutDir 'corrected'
$original=Join-Path $OutDir 'original'
$contract=Join-Path $OutDir 'contact-contract.json'
$stem='astermax-contact'

Write-Host 'CONTACT_STAGE: invoke ExportContract from the actual packaged executable'
$exported=Invoke-BenchmarkProcess $powershell @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $scripts 'export-compiled-contact.ps1'),'-Root',$Root,'-Dist',$Dist,'-Contract',$contract,'-OutDir',$corrected,'-BaseName',$stem) $OutDir (Join-Path $OutDir 'export') 180
Require-Success $exported 'Compiled production contact export'
$prepared=Invoke-BenchmarkProcess $python @((Join-Path $scripts 'prepare_contact_validation.py'),'--root',$OutDir) $OutDir (Join-Path $OutDir 'prepare') 60
Require-Success $prepared 'Production contact input validation'

if($PrepareOnly){
    Write-Host 'C12.07 packaged contact export preflight PASS; solver execution NOT_RUN.'
    return
}

Write-Host 'CONTACT_STAGE: require an already installed native Windows solver'
$probeRun=Invoke-BenchmarkProcess $powershell @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$runner,'probe') $OutDir (Join-Path $OutDir 'probe') 180
Require-Success $probeRun 'Native contact probe'
$probeRun.Stdout | Set-Content -LiteralPath (Join-Path $OutDir 'native-probe.json') -Encoding UTF8
$probe=$probeRun.Stdout | ConvertFrom-Json
if(-not $probe.ready -or $probe.transport -ne 'WINDOWS_NATIVE' -or $probe.wsl_required -ne $false){ throw 'Native contact smoke refuses a missing or non-native solver.' }

Write-Host 'CONTACT_STAGE: original orientations must fail with genuine CONTACT2_16'
$legacy=Invoke-BenchmarkProcess $powershell @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$runner,(Join-Path $original ($stem+'.export')),$original) $original (Join-Path $original 'runner')
$diagnostics=@(Get-ChildItem -LiteralPath $original -Recurse -File -Filter 'astermax-runner-diagnostic.json')
$diagnostic=$null
if($diagnostics.Count -eq 1){ $diagnostic=Get-Content -LiteralPath $diagnostics[0].FullName -Raw -Encoding UTF8 | ConvertFrom-Json }
[ordered]@{
    exit_code=$legacy.ExitCode
    marker=$(if($diagnostic){$diagnostic.marker}else{$null})
    contact_zones=$(if($diagnostic){@($diagnostic.contact_zones)}else{@()})
    shared_slave_nodes=$(if($diagnostic){$diagnostic.shared_slave_nodes}else{$null})
    backend_exit_code=$(if($diagnostic){$diagnostic.backend_exit_code}else{$null})
    solver_execution='RUN';synthetic_results_allowed=$false
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutDir 'negative-control.json') -Encoding UTF8
if($legacy.ExitCode -ne 31 -or -not $diagnostic -or $diagnostic.marker -ne 'CONTACT2_16'){
    throw "The legacy control did not reproduce CONTACT2_16 (exit $($legacy.ExitCode)); inspect original/runner logs and retained failed-* diagnostics."
}
if($diagnostic.shared_slave_nodes -ne 12){ throw 'The real CONTACT2_16 diagnostic did not report twelve shared slave nodes.' }
if((@($diagnostic.contact_zones) -join ',') -ne '1,2'){ throw 'The CONTACT2_16 diagnostic did not identify original solver zones 1 and 2.' }
if(Test-Path -LiteralPath (Join-Path $original ($stem+'.rmed'))){ throw 'A failed legacy solve promoted MED output.' }
if(Test-Path -LiteralPath (Join-Path $original ($stem+'.mess'))){ throw 'A failed legacy solve promoted its failed MESS as successful output.' }

Write-Host 'CONTACT_STAGE: solve production-oriented contacts with unchanged physics'
$solved=Invoke-BenchmarkProcess $powershell @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$runner,(Join-Path $corrected ($stem+'.export')),$corrected) $corrected (Join-Path $corrected 'runner')
[ordered]@{exit_code=$solved.ExitCode;solver_execution='RUN';transport='WINDOWS_NATIVE';synthetic_results_allowed=$false} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutDir 'corrected-run.json') -Encoding UTF8
Require-Success $solved 'Genuine corrected contact solve'

Write-Host 'CONTACT_STAGE: import final MED with the packaged production bridge'
$previousMode=$env:ASTERMAX_MED_BRIDGE_MODE
try {
    $env:ASTERMAX_MED_BRIDGE_MODE='production'
    $bridged=Invoke-BenchmarkProcess $python @($bridge,(Join-Path $corrected ($stem+'.rmed')),(Join-Path $corrected ($stem+'.astermax-results.json')),(Join-Path $corrected ($stem+'.astermax-results.vtu'))) $corrected (Join-Path $corrected 'med-bridge') 180
    Require-Success $bridged 'Packaged contact MED bridge'
}
finally { $env:ASTERMAX_MED_BRIDGE_MODE=$previousMode }

Write-Host 'CONTACT_STAGE: verify force equilibrium, table/MED agreement, and unchanged inputs'
$validated=Invoke-BenchmarkProcess $python @((Join-Path $scripts 'validate_contact_results.py'),'--root',$OutDir,'--executable',(Join-Path $Dist 'AsterMax Mechanical.exe')) $OutDir (Join-Path $OutDir 'validate') 120
Require-Success $validated 'Native contact numerical validation'
$report=Get-Content -LiteralPath (Join-Path $OutDir 'C12.07_NATIVE_CONTACT_VALIDATION.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if(-not $report.all_checks_pass){ throw 'Native contact validation did not pass every declared check.' }
Write-Host ('C1207_NATIVE_CONTACT_PASS checks='+$report.checks_passed+'/'+$report.checks_total+' original_shared_slave_nodes=12 exported_shared_slave_nodes=0')
Write-Host ('C1207_CONTACT_REACTION_N='+($report.observed.reaction_n -join ',')+' equilibrium_relative_error='+($report.observed.force_equilibrium_relative_error -join ','))
