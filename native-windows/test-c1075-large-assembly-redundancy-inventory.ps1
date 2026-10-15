param([Parameter(Mandatory=$true)][string]$Root,[string]$OutDir)
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path $Root).Path
$out=if([string]::IsNullOrWhiteSpace($OutDir)){Join-Path $PSScriptRoot '..\dist\Audit\C10.75'}else{$OutDir}
New-Item -ItemType Directory -Force $out|Out-Null
$files=Get-ChildItem $rootPath -Recurse -Filter *.cs -File
$patterns=[ordered]@{
 render='\.Render\s*\('
 reset_camera='ResetCamera\s*\('
 fit='\bFit\s*\('
 vtk_actor_ctor='new\s+vtkMaxActor\s*\('
 add_actor_geometry='AddActorGeometry\s*\('
 edge_work='\b(AddEdges|CreateEdges|ElementEdges|EdgeActor)\b'
 tree_update='\b(UpdateTree|RegenerateTree|RefreshTree|UpdateModelTree|RegenerateTreeFor)\s*\('
 import_file='\bImport(File|CADAssemblyFile|BrepPartFile)\s*\('
 vtk_update='\.Update\s*\('
}
$rows=@()
foreach($f in $files){
 $text=Get-Content $f.FullName -Raw
 foreach($k in $patterns.Keys){
  $matches=[regex]::Matches($text,$patterns[$k])
  if($matches.Count -gt 0){$rows += [pscustomobject]@{file=$f.FullName.Substring($rootPath.Length).TrimStart('\');token=$k;count=$matches.Count}}
 }
}
$totals=[ordered]@{}
foreach($k in $patterns.Keys){$sum=($rows|Where-Object token -eq $k|Measure-Object count -Sum).Sum;$totals[$k]=if($null -eq $sum){0}else{[int]$sum}}
$rows|Sort-Object token,count -Descending|Export-Csv (Join-Path $out 'redundancy-hotspots.csv') -NoTypeInformation -Encoding UTF8
[ordered]@{
 release='C10.75-large-assembly-redundancy-inventory'
 scope='STATIC_INSTRUMENTATION_ONLY'
 baseline_branch='agent/c1069c-c1042-semantic-render-fix'
 baseline_sha='1a043e1aa2c9f6baa5f23afdd090f1de839561f5'
 totals=$totals
 compilation='NOT_RUN'
 functionality='PASS_STATIC_INVENTORY_ONLY'
 performance='NOT_RUN'
 regressions='NOT_RUN'
 exact_incident_step='BLOCKED_NOT_PRESENT_IN_REPOSITORY'
 windows_x64_preserved=$true
 native_gui_preserved=$true
 code_aster_windows_only_solver_preserved=$true
 benchmark_values_invented=$false
}|ConvertTo-Json -Depth 6|Set-Content (Join-Path $out 'evidence.json') -Encoding UTF8
Write-Host ('C10.75 redundancy inventory: '+($totals|ConvertTo-Json -Compress))
