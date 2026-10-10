param([string]$BuildRoot)
$ErrorActionPreference='Stop'
$c=Get-Content (Join-Path $BuildRoot 'PrePoMax/Controller.cs') -Raw
$checks=[ordered]@{
  'isolated process scratch directory'=$c.Contains('"AsterMaxVis_" + Guid.NewGuid().ToString("N")')
  'NetGen working directory isolated'=$c.Contains('psi.WorkingDirectory = processWorkDirectory;')
  'scratch cleanup'=$c.Contains('Directory.Delete(processWorkDirectory, true);')
  'default workers two'=$c.Contains('int workers = Math.Min(2, Math.Max(1, Environment.ProcessorCount));')
  'configured workers cap four'=$c.Contains('workers = Math.Max(1, Math.Min(4, configuredWorkers));')
  'model remains serial'=$c.Contains('addedPartNames = AsterMaxImportPreparedBrep(asterMaxPrepared);')
}
$failed=@($checks.GetEnumerator()|Where-Object{-not $_.Value})
foreach($item in $checks.GetEnumerator()){$status=if($item.Value){'PASS'}else{'FAIL'};Write-Host ($status+' - '+$item.Key)}
if($failed.Count -gt 0){throw ('C10.45b static regression failed: '+(($failed|ForEach-Object{$_.Key}) -join ', '))}
Write-Host 'C10.45b static regression PASS.' -ForegroundColor Green
