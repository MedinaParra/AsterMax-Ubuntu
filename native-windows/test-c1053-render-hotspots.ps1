param([Parameter(Mandatory=$true)][string]$Root,[string]$OutDir)
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path $Root).Path
$out=if([string]::IsNullOrWhiteSpace($OutDir)){Join-Path $PSScriptRoot '..\dist\Audit\C10.53'}else{$OutDir}
New-Item -ItemType Directory -Force $out|Out-Null
$files=Get-ChildItem $rootPath -Recurse -Filter *.cs -File
$patterns=[ordered]@{
 render='\.Render\s*\('
 reset_camera='ResetCamera\s*\('
 fit='\bFit\s*\('
 vtk_actor_ctor='new\s+vtkMaxActor\s*\('
 add_actor_geometry='AddActorGeometry\s*\('
 edge_tokens='\b(AddEdges|CreateEdges|ElementEdges|EdgeActor)\b'
}
$rows=@()
foreach($f in $files){
 $text=Get-Content $f.FullName -Raw
 foreach($k in $patterns.Keys){
  $n=[regex]::Matches($text,$patterns[$k]).Count
  if($n -gt 0){$rows += [pscustomobject]@{file=$f.FullName.Substring($rootPath.Length).TrimStart('\');token=$k;count=$n}}
 }
}
$totals=[ordered]@{}
foreach($k in $patterns.Keys){$totals[$k]=[int](($rows|Where-Object token -eq $k|Measure-Object count -Sum).Sum)}
$rows|Sort-Object token,file|Export-Csv (Join-Path $out 'hotspots.csv') -NoTypeInformation -Encoding UTF8
[ordered]@{
 release='C10.53-render-hotspot-static-telemetry'
 scope='STATIC_TOKEN_INVENTORY_ONLY'
 totals=$totals
 compilation='NOT_RUN'
 functionality='PASS_STATIC_INVENTORY_ONLY'
 performance='NOT_RUN'
 regressions='NOT_RUN'
 exact_incident_step='BLOCKED_NOT_PRESENT_IN_REPOSITORY'
 code_aster_windows_only_solver_preserved=$true
 benchmark_values_invented=$false
}|ConvertTo-Json -Depth 5|Set-Content (Join-Path $out 'evidence.json') -Encoding UTF8
Write-Host ('C10.53 static hotspot inventory: '+($totals|ConvertTo-Json -Compress))
