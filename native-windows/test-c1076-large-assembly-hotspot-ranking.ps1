param([Parameter(Mandatory=$true)][string]$Root,[string]$OutDir)
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path $Root).Path
$out=if([string]::IsNullOrWhiteSpace($OutDir)){Join-Path $PSScriptRoot '..\dist\Audit\C10.76'}else{$OutDir}
New-Item -ItemType Directory -Force $out|Out-Null
$patterns=[ordered]@{
 render='\.Render\s*\('
 reset_camera='ResetCamera\s*\('
 vtk_actor_ctor='new\s+vtkMaxActor\s*\('
 add_actor_geometry='AddActorGeometry\s*\('
 edge_work='\b(AddEdges|CreateEdges|ElementEdges|EdgeActor)\b'
 tree_update='\b(UpdateTree|RegenerateTree|RefreshTree|UpdateModelTree|RegenerateTreeFor)\s*\('
 import_file='\bImport(File|CADAssemblyFile|BrepPartFile)\s*\('
 vtk_update='\.Update\s*\('
}
$weights=@{render=8;reset_camera=8;vtk_actor_ctor=3;add_actor_geometry=6;edge_work=4;tree_update=5;import_file=7;vtk_update=3}
$rows=@()
Get-ChildItem $rootPath -Recurse -Filter *.cs -File|ForEach-Object{
 $f=$_;$lines=Get-Content $f.FullName
 for($i=0;$i -lt $lines.Count;$i++){
  foreach($k in $patterns.Keys){
   if($lines[$i] -match $patterns[$k]){
    $rows += [pscustomobject]@{file=$f.FullName.Substring($rootPath.Length).TrimStart('\');line=$i+1;token=$k;weight=$weights[$k];text=$lines[$i].Trim()}
   }
  }
 }
}
$rows|Sort-Object file,line,token|Export-Csv (Join-Path $out 'hotspot-lines.csv') -NoTypeInformation -Encoding UTF8
$ranked=$rows|Group-Object file|ForEach-Object{
 $g=$_.Group
 [pscustomobject]@{file=$_.Name;score=[int](($g|Measure-Object weight -Sum).Sum);hits=$g.Count;render=($g|Where-Object token -eq render).Count;reset_camera=($g|Where-Object token -eq reset_camera).Count;vtk_actor_ctor=($g|Where-Object token -eq vtk_actor_ctor).Count;add_actor_geometry=($g|Where-Object token -eq add_actor_geometry).Count;edge_work=($g|Where-Object token -eq edge_work).Count;tree_update=($g|Where-Object token -eq tree_update).Count;import_file=($g|Where-Object token -eq import_file).Count;vtk_update=($g|Where-Object token -eq vtk_update).Count}
}|Sort-Object score -Descending
$ranked|Export-Csv (Join-Path $out 'hotspot-files-ranked.csv') -NoTypeInformation -Encoding UTF8
$top=@($ranked|Select-Object -First 15)
$top|ConvertTo-Json -Depth 4|Set-Content (Join-Path $out 'top15.json') -Encoding UTF8
[ordered]@{release='C10.76-large-assembly-hotspot-ranking';scope='STATIC_RANKING_ONLY';source_branch='agent/c1075-large-assembly-perf-instrumentation';compilation='NOT_RUN';functionality='PASS_STATIC_RANKING_ONLY';performance='NOT_RUN';regressions='NOT_RUN';exact_incident_step='BLOCKED_NOT_PRESENT_IN_REPOSITORY';weights=$weights;top15=$top;benchmark_values_invented=$false}|ConvertTo-Json -Depth 8|Set-Content (Join-Path $out 'evidence.json') -Encoding UTF8
Write-Host 'C10.76 TOP HOTSPOTS'
$top|Format-Table -AutoSize
