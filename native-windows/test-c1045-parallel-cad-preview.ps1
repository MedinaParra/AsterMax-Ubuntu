param([string]$BuildRoot)
$ErrorActionPreference='Stop'
$c=Get-Content (Join-Path $BuildRoot 'PrePoMax/Controller.cs') -Raw
$checks=[ordered]@{
  'prepared visualization DTO'=$c.Contains('private sealed class AsterMaxPreparedBrepVisualization')
  'unique VIS per worker'=$c.Contains('Tools.GetNonExistentRandomFileName(workDirectory, ".vis")')
  'bounded worker environment'=$c.Contains('ASTERMAX_CAD_TESSELLATION_WORKERS')
  'worker hard cap 8'=$c.Contains('Math.Max(1, Math.Min(8, configuredWorkers))')
  'default max 4 workers'=$c.Contains('Math.Min(4, Math.Max(1, Environment.ProcessorCount))')
  'parallel only prepares VIS'=$c.Contains('System.Threading.Tasks.Parallel.ForEach(leaves, options')
  'model import outside parallel helper'=$c.Contains('private string[] AsterMaxImportPreparedBrep(')
  'serial prepared model import'=$c.Contains('addedPartNames = AsterMaxImportPreparedBrep(asterMaxPrepared);')
  'compound path retained'=$c.Contains('ImportBrepCompoundPart(partFileName, null, out string compoundPartName, out addedPartNames);')
  'parallel telemetry'=$c.Contains('AsterMax CAD parallel preview:')
  'VIS cleanup'=$c.Contains('File.Delete(prepared.VisFileName);')
}
$failed=@($checks.GetEnumerator()|Where-Object{-not $_.Value})
foreach($item in $checks.GetEnumerator()){$status=if($item.Value){'PASS'}else{'FAIL'};Write-Host ($status+' - '+$item.Key)}
if($failed.Count -gt 0){throw ('C10.45 static regression failed: '+(($failed|ForEach-Object{$_.Key}) -join ', '))}
Write-Host 'C10.45 static regression PASS.' -ForegroundColor Green
