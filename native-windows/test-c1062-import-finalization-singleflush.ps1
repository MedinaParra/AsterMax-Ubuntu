param([string]$Root = ".")
$ErrorActionPreference='Stop'

# Static source guard for the CAD import finalization path.
# Goal: prevent future patches from reintroducing camera/render/tree work into
# progress reporting or multiple final scene flushes. This is NOT a benchmark.
$progress=Join-Path $Root 'PrePoMax/AsterMaxProgressDialog.cs'
$controller=Join-Path $Root 'PrePoMax/Controller.cs'
$vtk=Join-Path $Root 'vtkControl/vtkControl.cs'
foreach($p in @($progress,$controller,$vtk)){if(-not(Test-Path $p)){throw "C10.62 missing patched source: $p"}}

$ptext=[IO.File]::ReadAllText($progress)
$ctext=[IO.File]::ReadAllText($controller)
$vtext=[IO.File]::ReadAllText($vtk)

$forbiddenProgress=@('Render\s*\(','ResetCamera\s*\(','AdjustCameraDistanceAndClippingRedraw\s*\(','DrawGeometry\s*\(','RegenerateTree','UpdateTree','RebuildTree','PopulateTree','Add3DCells','AddCells\s*\(','ElementEdges','EdgeActor')
$progressHits=[ordered]@{}
foreach($pattern in $forbiddenProgress){$progressHits[$pattern]=[regex]::Matches($ptext,$pattern,[Text.RegularExpressions.RegexOptions]::IgnoreCase).Count}
$badProgress=@($progressHits.GetEnumerator()|Where-Object Value -gt 0)

$beginCount=[regex]::Matches($ctext,'AsterMaxBeginVtkSceneBatch\s*\(').Count
$endCount=[regex]::Matches($ctext,'AsterMaxEndVtkSceneBatch\s*\(').Count
$deferCount=[regex]::Matches($vtext,'_asterMaxSceneBatchDeferredCameraAdjusts\+\+').Count
$flushCount=[regex]::Matches($vtext,'_asterMaxSceneBatchCameraFlushes\+\+').Count

$batchPass=($beginCount -eq 1 -and $endCount -eq 1 -and $deferCount -eq 1 -and $flushCount -eq 1)
$progressPass=($badProgress.Count -eq 0)

$out=Join-Path $PSScriptRoot '../dist/Audit/C10.62';New-Item -ItemType Directory -Force $out|Out-Null
[ordered]@{
 release='C10.62-import-finalization-singleflush-guard';
 scope='STATIC_GUARD_ONLY';
 progress_viewport_purity=if($progressPass){'PASS'}else{'FAIL'};
 scene_batch_structure=if($batchPass){'PASS'}else{'FAIL'};
 scene_batch_begin_calls=$beginCount;
 scene_batch_end_calls=$endCount;
 deferred_camera_increment_sites=$deferCount;
 camera_flush_increment_sites=$flushCount;
 progress_forbidden_hits=$progressHits;
 compilation='NOT_RUN';
 functionality=if($progressPass -and $batchPass){'PASS_STATIC_GUARD_ONLY'}else{'FAIL_STATIC_GUARD'};
 performance='NOT_RUN';
 regressions=if($progressPass -and $batchPass){'PASS_STATIC_GUARD_ONLY'}else{'FAIL_STATIC_GUARD'};
 exact_incident_step='BLOCKED_NOT_PRESENT_IN_REPOSITORY';
 code_aster_windows_only_solver_preserved=$true;
 benchmark_values_invented=$false
}|ConvertTo-Json -Depth 6|Set-Content (Join-Path $out 'evidence.json') -Encoding UTF8

if(-not $progressPass){throw 'C10.62: progress UI contains viewport/tree/actor work.'}
if(-not $batchPass){throw "C10.62: expected exactly one CAD scene batch/flush structure; begin=$beginCount end=$endCount defer=$deferCount flush=$flushCount"}
Write-Host 'PASS C10.62: progress remains viewport-pure and CAD scene batching has one begin/end plus one deferred-camera/flush site.'
