param([string]$BuildRoot)
$ErrorActionPreference='Stop'

$c=Get-Content (Join-Path $BuildRoot 'PrePoMax/Controller.cs') -Raw
$u=Get-Content (Join-Path $BuildRoot 'PrePoMax/Forms/AsterMaxNativeUi.cs') -Raw
$p=Get-Content (Join-Path $BuildRoot 'PrePoMax/PrePoMax.csproj') -Raw
$auditPath=Join-Path $BuildRoot 'PrePoMax/Forms/AsterMaxC1043ImportAudit.cs'

$checks=[ordered]@{
  'unique visualization file'=$c.Contains('Tools.GetNonExistentRandomFileName(calculixSettings.WorkDirectory, ".vis")')
  'unique NetGen job name'=$c.Contains('string jobName = "Brep_" + visStem;')
  'VIS existence validation'=$c.Contains('visualization file is missing or empty')
  'VIS cleanup'=$c.Contains('if (File.Exists(visFileName)) File.Delete(visFileName);')
  'tessellation PASS telemetry'=$c.Contains('AsterMax CAD tessellation PASS:')
  'split empty diagnostic'=$c.Contains('ASTERMAX_CAD_SPLIT_EMPTY')
  'import empty diagnostic'=$c.Contains('ASTERMAX_CAD_IMPORT_EMPTY')
  'partial import diagnostic'=$c.Contains('ASTERMAX_CAD_IMPORT_PARTIAL')
  'complete import diagnostic'=$c.Contains('ASTERMAX_CAD_IMPORT_COMPLETE')
  'empty compound rejected'=$c.Contains('AsterMax compound import produced no geometry.')
  'runtime audit source'=Test-Path $auditPath
  'runtime audit compiled'=$p.Contains('Forms\AsterMaxC1043ImportAudit.cs')
  'runtime audit started'=$u.Contains('StartAsterMaxC1043ImportAudit();')
}
$failed=@($checks.GetEnumerator() | Where-Object {-not $_.Value})
foreach($item in $checks.GetEnumerator()){
  $status=if($item.Value){'PASS'}else{'FAIL'}
  Write-Host ($status+' - '+$item.Key)
}
if($failed.Count -gt 0){throw ('C10.43 static regression failed: '+(($failed|ForEach-Object{$_.Key}) -join ', '))}
Write-Host 'C10.43 static regression PASS.' -ForegroundColor Green
