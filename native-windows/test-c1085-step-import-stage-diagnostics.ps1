param([string]$Root)
$ErrorActionPreference='Stop'
$controller=Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $controller)){throw "C10.85 test missing: $controller"}
$c=Get-Content $controller -Raw
$checks=[ordered]@{
  'argument stage telemetry'='ASTERMAX_CAD_STAGE=ARG_READY'
  'NetGen submit telemetry'='ASTERMAX_CAD_STAGE=NETGEN_SUBMIT'
  'NetGen return telemetry'='ASTERMAX_CAD_STAGE=NETGEN_RETURN'
  'VIS parse start telemetry'='ASTERMAX_CAD_STAGE=VIS_PARSE_START'
  'VIS parse pass telemetry'='ASTERMAX_CAD_STAGE=VIS_PARSE_PASS'
  'VIS FormatException stage telemetry'='ASTERMAX_CAD_FORMAT_EXCEPTION stage=VIS_PARSE'
  'culture captured'='CultureInfo.CurrentCulture.Name'
  'UI culture captured'='CultureInfo.CurrentUICulture.Name'
  'FormatException caught specifically'='catch (FormatException ex)'
}
foreach($kv in $checks.GetEnumerator()){
  if(!$c.Contains($kv.Value)){throw "FAIL - $($kv.Key): missing $($kv.Value)"}
  Write-Host "PASS - $($kv.Key)"
}
if($c.Contains('GeometryDeflection.ToString();')){throw 'FAIL - current-culture direct GeometryDeflection.ToString() remains in final controller.'}
Write-Host 'C10.85 static diagnostic contract PASS.' -ForegroundColor Green
