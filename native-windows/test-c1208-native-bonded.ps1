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
if([string]::IsNullOrWhiteSpace($OutDir)){ $OutDir=Join-Path $Dist 'Validation/C12.08-Native-Bonded' }
if(Test-Path -LiteralPath $OutDir){
    if(@(Get-ChildItem -LiteralPath $OutDir -Force).Count -gt 0){ throw 'Bonded validation requires a fresh output directory.' }
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir=(Resolve-Path -LiteralPath $OutDir).Path
$python=Join-Path $Dist 'AsterMaxRuntime/Python/python.exe'
$runner=Join-Path $Dist 'AsterMaxRuntime/CodeAster/astermax-codeaster-runner.ps1'
$bridge=Join-Path $Dist 'AsterMaxTools/bridge-c964-med-results.py'
$powershell=Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$scripts=Join-Path $PSScriptRoot 'c1208-bonded'
# This established helper invokes generic ExportContract from the packaged EXE,
# resolves dependencies only within the package, and checks source immutability.
$compiledExporter=Join-Path $PSScriptRoot 'c1207-contact/export-compiled-contact.ps1'
foreach($file in @($python,$runner,$bridge,$powershell,$compiledExporter)){
    if(-not (Test-Path -LiteralPath $file -PathType Leaf)){ throw "Native bonded prerequisite missing: $file" }
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
        # Preserve the C12.07 fix: Windows PowerShell must rebuild its own
        # module path instead of inheriting PowerShell 7 module directories.
        $process.StartInfo.EnvironmentVariables.Remove('PSModulePath')
    }
    try {
        if(-not $process.Start()){ throw "Unable to start $Program" }
        $stdout=$process.StandardOutput.ReadToEndAsync()
        $stderr=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit($TimeoutSeconds*1000)){
            & "$env:SystemRoot/System32/taskkill.exe" /PID $process.Id /T /F | Out-Null
            throw "Bonded benchmark process timed out: $Program"
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

Write-Host 'BONDED_STAGE: generate nonmatching tetrahedra, shared slave edge, and a 2.5 mm gap'
$generated=Invoke-BenchmarkProcess $python @((Join-Path $scripts 'generate_bonded_fixture.py'),'--out',$OutDir) $OutDir (Join-Path $OutDir 'generate') 60
Require-Success $generated 'Bonded fixture generation'
$stem='astermax-bonded'
foreach($case in @('force','rotation')){
    $caseRoot=Join-Path $OutDir $case
    $output=Join-Path $caseRoot 'exported'
    $contract=Join-Path $caseRoot 'bonded-contract.json'
    Write-Host "BONDED_STAGE: invoke the compiled packaged exporter for $case"
    $exported=Invoke-BenchmarkProcess $powershell @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$compiledExporter,'-Root',$Root,'-Dist',$Dist,'-Contract',$contract,'-OutDir',$output,'-BaseName',$stem) $caseRoot (Join-Path $caseRoot 'export') 180
    Require-Success $exported "Compiled production bonded $case export"
}
$prepared=Invoke-BenchmarkProcess $python @((Join-Path $scripts 'prepare_bonded_validation.py'),'--root',$OutDir) $OutDir (Join-Path $OutDir 'prepare') 120
Require-Success $prepared 'Independent bonded MPC, rank, and affine-invariance preflight'
if($PrepareOnly){
    Write-Host 'C12.08 packaged bonded export preflight PASS; solver execution NOT_RUN.'
    return
}

Write-Host 'BONDED_STAGE: require an already installed native Windows solver'
$probeRun=Invoke-BenchmarkProcess $powershell @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$runner,'probe') $OutDir (Join-Path $OutDir 'probe') 180
Require-Success $probeRun 'Native bonded probe'
$probeRun.Stdout | Set-Content -LiteralPath (Join-Path $OutDir 'native-probe.json') -Encoding UTF8
$probe=$probeRun.Stdout | ConvertFrom-Json
if(-not $probe.ready -or $probe.transport -ne 'WINDOWS_NATIVE' -or $probe.wsl_required -ne $false){ throw 'Bonded admission refuses a missing or non-native solver.' }

foreach($case in @('force','rotation')){
    $caseRoot=Join-Path $OutDir $case
    $output=Join-Path $caseRoot 'exported'
    Write-Host "BONDED_STAGE: solve the production $case deck with genuine native Code_Aster"
    $solved=Invoke-BenchmarkProcess $powershell @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$runner,(Join-Path $output ($stem+'.export')),$output) $output (Join-Path $output 'runner')
    [ordered]@{exit_code=$solved.ExitCode;solver_execution='RUN';transport='WINDOWS_NATIVE';synthetic_results_allowed=$false} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $caseRoot 'native-run.json') -Encoding UTF8
    Require-Success $solved "Genuine bonded $case solve"
    Write-Host "BONDED_STAGE: import the actual $case MED using the packaged production bridge"
    $previousMode=$env:ASTERMAX_MED_BRIDGE_MODE
    try {
        $env:ASTERMAX_MED_BRIDGE_MODE='production'
        $bridged=Invoke-BenchmarkProcess $python @($bridge,(Join-Path $output ($stem+'.rmed')),(Join-Path $output ($stem+'.astermax-results.json')),(Join-Path $output ($stem+'.astermax-results.vtu'))) $output (Join-Path $output 'med-bridge') 180
        Require-Success $bridged "Packaged bonded $case MED bridge"
    }
    finally { $env:ASTERMAX_MED_BRIDGE_MODE=$previousMode }
}

Write-Host 'BONDED_STAGE: validate force/moment balance, rigid rotation, every MPC, and every MED/table node'
$validated=Invoke-BenchmarkProcess $python @((Join-Path $scripts 'validate_bonded_results.py'),'--root',$OutDir,'--executable',(Join-Path $Dist 'AsterMax Mechanical.exe')) $OutDir (Join-Path $OutDir 'validate') 120
Require-Success $validated 'Native bonded numerical validation'
$report=Get-Content -LiteralPath (Join-Path $OutDir 'C12.08_NATIVE_BONDED_VALIDATION.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if(-not $report.all_checks_pass){ throw 'Native bonded validation did not pass every declared check.' }
Write-Host ('C1208_NATIVE_BONDED_PASS checks='+$report.checks_passed+'/'+$report.checks_total+' shared_slave_nodes=4 gap_mm=2.5')
foreach($case in $report.cases){
    Write-Host ('C1208_BONDED_CASE='+$case.case+' checks_pass='+$case.all_checks_pass+' reaction_n='+($case.observed.reaction_n -join ','))
}
