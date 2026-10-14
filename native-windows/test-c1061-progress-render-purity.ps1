param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$progress=Join-Path $Root 'PrePoMax\AsterMaxProgressDialog.cs'
if(-not(Test-Path $progress)){throw 'AsterMaxProgressDialog.cs missing; apply C10.60 first.'}
$c=Get-Content $progress -Raw
$forbidden=[ordered]@{
 render='\.Render\s*\('
 reset_camera='ResetCamera\s*\('
 fit='\bFit\s*\('
 vtk_actor='vtkMaxActor|AddActorGeometry|Add3DCells'
 tree_rebuild='RegenerateTree|UpdateTree|RebuildTree|PopulateTree'
 edge_work='AddEdges|CreateEdges|ElementEdges|EdgeActor'
}
$hits=[ordered]@{}
foreach($k in $forbidden.Keys){$hits[$k]=[regex]::Matches($c,$forbidden[$k],[Text.RegularExpressions.RegexOptions]::IgnoreCase).Count}
$bad=@($hits.GetEnumerator()|Where-Object Value -gt 0)
if($bad.Count -gt 0){throw ('Progress UI contains forbidden viewport/tree work: '+(($bad|ForEach-Object{"$($_.Key)=$($_.Value)"}) -join ', '))}
if(-not $c.Contains('_uiTimer.Interval=250')){throw 'Expected throttled 250 ms elapsed UI cadence missing.'}
if($c -match '_uiTimer\.Tick[\s\S]{0,300}(_bar\.Value|Report\()'){throw 'Timer must not synthesize progress or invoke reporting.'}
$out=Join-Path $PSScriptRoot '..\dist\Audit\C10.61';New-Item -ItemType Directory -Force $out|Out-Null
[ordered]@{release='C10.61-progress-render-purity';scope='STATIC_GUARD_ONLY';forbidden_hits=$hits;ui_elapsed_refresh_ms=250;compilation='NOT_RUN';functionality='PASS_STATIC_GUARD_ONLY';performance='NOT_RUN';regressions='NOT_RUN';exact_incident_step='BLOCKED_NOT_PRESENT_IN_REPOSITORY';code_aster_windows_only_solver_preserved=$true;benchmark_values_invented=$false}|ConvertTo-Json -Depth 5|Set-Content (Join-Path $out 'evidence.json') -Encoding UTF8
Write-Host 'PASS C10.61: progress UI has no direct render/camera/tree/actor/edge work.'