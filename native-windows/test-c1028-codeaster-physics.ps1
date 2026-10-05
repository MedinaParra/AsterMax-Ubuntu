param(
    [Parameter(Mandatory=$true)][string]$Dist
)
$ErrorActionPreference='Stop'

$runner=(Resolve-Path (Join-Path $PSScriptRoot 'runtime\CodeAster\astermax-codeaster-runner.ps1')).Path
$bridge=(Resolve-Path (Join-Path $PSScriptRoot 'bridge-c964-med-results.py')).Path
$qualifier=(Resolve-Path (Join-Path $PSScriptRoot 'qualify-mechanical-analysis.py')).Path

function Write-AsterExport([string]$Dir,[string]$Base) {
    $path=Join-Path $Dir ($Base+'.export')
    $text=@(
        'P actions make_etude',
        'P version stable',
        'P mode interactif',
        'P time_limit 300',
        'P memory_limit 2048',
        'P ncpus 1',
        'P mpi_nbcpu 1',
        '',
        ('F comm /analysis/'+$Base+'.comm D 1'),
        ('F mail /analysis/'+$Base+'.mail D 20'),
        ('F mess /analysis/'+$Base+'.mess R 6'),
        ('F resu /analysis/'+$Base+'.resu R 80'),
        ('F rmed /analysis/'+$Base+'.rmed R 81')
    ) -join "`r`n"
    [IO.File]::WriteAllText($path,$text+"`r`n",(New-Object System.Text.UTF8Encoding($false)))
    return $path
}

$cases=@(
    [ordered]@{label='pressure-frictionless';dir=(Join-Path $Dist 'Validation\C10.24-Surface-Exporter');base='surface-cube';equilibrium=$true},
    [ordered]@{label='surface-traction';dir=(Join-Path $Dist 'Validation\C10.26-Surface-Traction');base='traction-cube';equilibrium=$true},
    [ordered]@{label='multi-material';dir=(Join-Path $Dist 'Validation\C10.27-Multi-Material');base='multi-material';equilibrium=$true}
)

$summary=@()
foreach($case in $cases) {
    $dir=$case.dir; $base=$case.base
    if(-not(Test-Path $dir)){ throw "C10.28 case directory missing: $dir" }
    foreach($ext in @('comm','mail','native-export.json')) {
        $p=Join-Path $dir ($base+'.'+$ext)
        if(-not(Test-Path $p)){ throw "C10.28 input missing: $p" }
    }
    $export=Write-AsterExport $dir $base
    $stdout=Join-Path $dir ($base+'.solver-stdout.log')
    Write-Host "C10.28 SOLVE $($case.label)" -ForegroundColor Cyan
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runner $export $dir 2>&1 | Tee-Object $stdout
    if($LASTEXITCODE -ne 0){ throw "Code_Aster solve failed for $($case.label)." }

    $mess=Join-Path $dir ($base+'.mess')
    $rmed=Join-Path $dir ($base+'.rmed')
    if(-not(Test-Path $mess) -or (Get-Item $mess).Length -le 0){ throw "Missing non-empty .mess for $($case.label)." }
    if(-not(Test-Path $rmed) -or (Get-Item $rmed).Length -le 0){ throw "Missing non-empty .rmed for $($case.label)." }
    $messText=Get-Content $mess -Raw
    if($messText -notmatch 'ARRET\s+NORMAL'){ throw "Code_Aster .mess does not attest ARRET NORMAL for $($case.label)." }

    $bundle=Join-Path $dir ($base+'.astermax-results.json')
    $vtu=Join-Path $dir ($base+'.astermax-results.vtu')
    $env:ASTERMAX_MED_BRIDGE_MODE='production'
    & python $bridge $rmed $bundle $vtu
    if($LASTEXITCODE -ne 0){ throw "MED bridge failed for $($case.label)." }

    $manifest=Join-Path $dir ($base+'.native-export.json')
    $qualification=Join-Path $dir ($base+'.mechanical-qualification.json')
    & python $qualifier --bundle $bundle --analysis $manifest --mess $mess --out $qualification
    if($LASTEXITCODE -eq 2){ throw "Mechanical Qualification BLOCKED for $($case.label)." }
    if($LASTEXITCODE -ne 0){ throw "Mechanical Qualification failed for $($case.label)." }

    $q=Get-Content $qualification -Raw | ConvertFrom-Json
    $manifestObj=Get-Content $manifest -Raw | ConvertFrom-Json
    $eq=$q.findings | Where-Object {$_.code -eq 'GLOBAL_EQUILIBRIUM'} | Select-Object -First 1
    if($case.equilibrium -and $manifestObj.external_resultant_complete -ne $false) {
        if($null -eq $eq -or $eq.level -ne 'PASS'){
            throw "Global equilibrium did not PASS for $($case.label): $($eq | ConvertTo-Json -Compress)"
        }
    }
    $summary += [ordered]@{
        label=$case.label
        solver='Code_Aster Windows'
        arret_normal=$true
        rmed_bytes=(Get-Item $rmed).Length
        qualification=$q.status
        equilibrium_level=if($eq){$eq.level}else{$null}
        equilibrium_residual_pct=if($eq -and $eq.residual_pct -ne $null){[double]$eq.residual_pct}else{$null}
        fea_values_invented=$false
    }
}

$out=Join-Path $Dist 'Validation\C10.28-CODE_ASTER_PHYSICS_SMOKE.json'
[ordered]@{
    schema='astermax-c1028-codeaster-physics-smoke/v1'
    status='PASS'
    cases=$summary
    solver_execution='RUN'
    fea_values_invented=$false
} | ConvertTo-Json -Depth 8 | Set-Content $out -Encoding UTF8
Write-Host 'C10.28 genuine Code_Aster physics smoke PASS.' -ForegroundColor Green
