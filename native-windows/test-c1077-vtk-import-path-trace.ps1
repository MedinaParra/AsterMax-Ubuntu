param([Parameter(Mandatory=$true)][string]$Root,[string]$OutDir)
$ErrorActionPreference='Stop'
$root=(Resolve-Path $Root).Path
$out=if($OutDir){$OutDir}else{Join-Path $PSScriptRoot '..\dist\Audit\C10.77'}
New-Item -ItemType Directory -Force $out|Out-Null
$targets=@('PrePoMax\Controller.cs','vtkControl\vtkControl.cs','PrePoMax\Forms\AsterMaxNativeUi.cs')
$patterns=[ordered]@{
 import_cad='ImportCADAssemblyFile\s*\('
 update_after_import='UpdateAfterImport\s*\('
 draw_geometry='DrawGeometry\s*\('
 add_actor_geometry='AddActorGeometry\s*\('
 render_scene='RenderSceene\s*\('
 reset_camera='ResetCamera\s*\('
 zoom_fit='SetZoomToFit\s*\('
 isometric='SetIsometricView\s*\('
 edges='\b(AddEdges|CreateEdges|ElementEdges|EdgeActor|CurrentEdgesVisibility)\b'
 vtk_update='\.Update\s*\('
}
$rows=@()
foreach($rel in $targets){
 $path=Join-Path $root $rel
 if(!(Test-Path $path)){throw "C10.77 missing target: $rel"}
 $lines=Get-Content $path
 for($i=0;$i -lt $lines.Count;$i++){
  foreach($k in $patterns.Keys){if($lines[$i] -match $patterns[$k]){$rows += [pscustomobject]@{file=$rel;line=$i+1;token=$k;text=$lines[$i].Trim()}}}
 }
}
$rows|Sort-Object file,line,token|Export-Csv (Join-Path $out 'import-first-frame-sites.csv') -NoTypeInformation -Encoding UTF8
$summary=$rows|Group-Object file,token|ForEach-Object{[pscustomobject]@{file=$_.Group[0].file;token=$_.Group[0].token;count=$_.Count}}|Sort-Object file,token
$summary|Export-Csv (Join-Path $out 'import-first-frame-summary.csv') -NoTypeInformation -Encoding UTF8
# Contract checks prove that existing coalescing/deferred-finalization guards survived the cumulative patch chain.
$controller=Get-Content (Join-Path $root 'PrePoMax\Controller.cs') -Raw
$vtk=Get-Content (Join-Path $root 'vtkControl\vtkControl.cs') -Raw
$ui=Get-Content (Join-Path $root 'PrePoMax\Forms\AsterMaxNativeUi.cs') -Raw
$checks=[ordered]@{
 cad_depth_guard=$controller.Contains('_asterMaxCadImportDepth')
 top_level_transaction=$controller.Contains('asterMaxTopLevelCadImport')
 deferred_update=$controller.Contains('if (_asterMaxCadImportDepth == 0)')
 large_assembly_edges=$controller.Contains('ASTERMAX_LARGE_ASSEMBLY_PARTS')
 render_scheduled=$vtk.Contains('_asterMaxRenderScheduled')
 render_pending=$vtk.Contains('_asterMaxRenderPending')
 queued_paint=$vtk.Contains('one queued paint per message-loop turn')
 center_without_redraw=$ui.Contains('Geometry actors are already created by UpdateAfterImport. Do not redraw.')
}
$failed=@($checks.GetEnumerator()|Where-Object{-not $_.Value})
[ordered]@{release='C10.77-vtk-import-path-trace';scope='STATIC_IMPORT_TO_FIRST_FRAME_TRACE';checks=$checks;site_count=$rows.Count;performance='NOT_RUN';compilation='NOT_RUN';functionality=if($failed.Count -eq 0){'PASS_STATIC_CONTRACT'}else{'FAIL_STATIC_CONTRACT'};regressions='NOT_RUN';exact_step='BLOCKED_NOT_PRESENT';benchmark_values_invented=$false}|ConvertTo-Json -Depth 6|Set-Content (Join-Path $out 'evidence.json') -Encoding UTF8
Write-Host 'C10.77 import-to-first-frame site summary'
$summary|Format-Table -AutoSize
if($failed.Count -gt 0){throw ('C10.77 contract failure: '+(($failed|ForEach-Object{$_.Key}) -join ', '))}
Write-Host 'C10.77 static import/render contract PASS.' -ForegroundColor Green
