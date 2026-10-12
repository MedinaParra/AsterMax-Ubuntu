param([string]$Root)
$ErrorActionPreference='Stop'
$vtk=Join-Path $Root 'vtkControl/vtkControl.cs'
$actor=Join-Path $Root 'vtkControl/vtkMaxActor.cs'
foreach($p in @($vtk,$actor)){if(!(Test-Path $p)){throw "C10.50 missing: $p"}}
$v=Get-Content $vtk -Raw
$a=Get-Content $actor -Raw
$report=[ordered]@{
 vtk_control=$vtk
 vtk_actor=$actor
 add_cells_signatures=([regex]::Matches($v,'\bAddCells\s*\(')).Count
 add_actor_calls=([regex]::Matches($v,'\.AddActor\s*\(')).Count
 renderer_add_actor_calls=([regex]::Matches($v,'_renderer[^\r\n]*\.AddActor\s*\(')).Count
 render_calls=([regex]::Matches($v,'\.Render\s*\(')).Count
 reset_camera_calls=([regex]::Matches($v,'\.ResetCamera\s*\(')).Count
 mapper_mentions=([regex]::Matches($a,'vtk[^\s;]*Mapper')).Count
 polydata_mentions=([regex]::Matches($a,'vtkPolyData')).Count
 c1049_add_cells_counter=$v.Contains('AsterMaxSceneBatchAddCells')
 c1049_flush_counter=$v.Contains('AsterMaxSceneBatchRenderRequests')
 c1048_lazy_edges=$a.Contains('_asterMaxElementEdgesDeferred')
 application_doevents_count=([regex]::Matches($v,'Application\.DoEvents\s*\(')).Count
 interpretation='STATIC_PREFLIGHT_ONLY: inventories actor/mapper/render/camera pressure before any render-proxy mutation; counts are source occurrences, not runtime calls or performance results.'
}
$out=Join-Path (Split-Path $Root -Parent) 'dist/Audit/C10.50'
New-Item -ItemType Directory -Force $out|Out-Null
$report|ConvertTo-Json -Depth 4|Set-Content (Join-Path $out 'render-proxy-preflight.json') -Encoding UTF8
$report|ConvertTo-Json -Depth 4
if(-not $report.c1049_add_cells_counter -or -not $report.c1049_flush_counter){throw 'C10.50 requires validated C10.49 instrumentation.'}
if(-not $report.c1048_lazy_edges){throw 'C10.50 requires C10.48 lazy-edge state.'}
Write-Host 'C10.50 preflight PASS: architecture inventoried without mutating visualization behavior.' -ForegroundColor Green
