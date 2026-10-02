param([Parameter(Mandatory=$true)][string]$Dist)
$ErrorActionPreference='Stop'
$runner=(Resolve-Path (Join-Path $PSScriptRoot 'runtime\CodeAster\astermax-codeaster-runner.ps1')).Path
$bridge=(Resolve-Path (Join-Path $PSScriptRoot 'bridge-c964-med-results.py')).Path
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

$dir=Join-Path $Dist 'Validation\Static-History-v2'
$summary=@()
foreach($base in @('independent-loads','displacement-only')) {
    $export=Write-AsterExport $dir $base
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runner $export $dir 2>&1 | Tee-Object (Join-Path $dir ($base+'.solver.log'))
    if($LASTEXITCODE -ne 0){ throw "Native Code_Aster failed: $base" }
    $mess=Get-Content (Join-Path $dir ($base+'.mess')) -Raw
    if($mess -notmatch 'ARRET\s+NORMAL'){ throw "No normal termination: $base" }
    $env:ASTERMAX_MED_BRIDGE_MODE='production'
    $env:ASTERMAX_MED_STEP_SELECTION='last'
    $bundle=Join-Path $dir ($base+'.astermax-results.json')
    & python $bridge (Join-Path $dir ($base+'.rmed')) $bundle (Join-Path $dir ($base+'.vtu'))
    if($LASTEXITCODE -ne 0){ throw "MED result admission failed: $base" }
    $b=Get-Content $bundle -Raw | ConvertFrom-Json
    if($b.source.kind -ne 'REAL_CODE_ASTER_MED' -or $b.integrity.fea_values_invented -ne $false){ throw 'Invalid solver provenance.' }
    $expectedTime=if($base -eq 'independent-loads'){2.0}else{1.0}
    if([Math]::Abs([double]$b.source.med_result_time-$expectedTime) -gt 1e-10){ throw 'Wrong result instant.' }
    $r=@($b.fields.reaction.resultant_n)
    if($r.Count -ne 3){ throw 'Reaction evidence missing.' }
    if($base -eq 'independent-loads') {
        $expected=@(540.0,50.0,-100.0)
        $sum=0.0
        for($i=0;$i -lt 3;$i++){ $sum+=[Math]::Pow([double]$r[$i]+$expected[$i],2) }
        if([Math]::Sqrt($sum) -gt 0.01){ throw 'Mixed constant/variable loads do not balance their independently expected resultant.' }
    } else {
        if([Math]::Abs([double]$b.fields.displacement.dx_max-0.5) -gt 1e-6){ throw 'Prescribed final displacement not respected.' }
        if([double]$b.fields.von_mises.nodal_max -le 0){ throw 'Displacement-only model produced no stress.' }
        if(($r | Where-Object { [Math]::Abs([double]$_) -gt 0.01 }).Count -gt 0){ throw 'Displacement-only model reactions do not self-balance.' }
    }
    $summary+=[ordered]@{case=$base;status='PASS';time=$b.source.med_result_time;dx_max_mm=$b.fields.displacement.dx_max;reaction_resultant_n=$r;solver_execution='RUN'}
}
[ordered]@{status='PASS';cases=$summary;solver='native Windows Code_Aster';fea_values_invented=$false} | ConvertTo-Json -Depth 8 |
    Set-Content (Join-Path $dir 'STATIC_HISTORY_V2_PHYSICS.json') -Encoding UTF8
