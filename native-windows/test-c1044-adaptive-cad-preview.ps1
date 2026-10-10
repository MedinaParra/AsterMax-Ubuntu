param([string]$BuildRoot)
$ErrorActionPreference='Stop'
$c=Get-Content (Join-Path $BuildRoot 'PrePoMax/Controller.cs') -Raw
$checks=[ordered]@{
  'preview override field'=$c.Contains('private double? _asterMaxCadVisualizationDeflectionOverride;')
  'large assembly deflection env'=$c.Contains('ASTERMAX_LARGE_ASSEMBLY_DEFLECTION')
  'default adaptive deflection 0.04'=$c.Contains('Math.Max(_settings.Graphics.GeometryDeflection, 0.04)')
  'deflection capped at 0.1'=$c.Contains('Math.Min(0.1, Math.Max(')
  'preview override consumed'=$c.Contains('_asterMaxCadVisualizationDeflectionOverride ??')
  'invariant NetGen numeric format'=$c.Contains('asterMaxVisualDeflection.ToString(System.Globalization.CultureInfo.InvariantCulture)')
  'exact BREP retained telemetry'=$c.Contains('Exact BREP retained.')
  'override reset after transaction'=$c.Contains('if (asterMaxTopLevelCadImport) _asterMaxCadVisualizationDeflectionOverride = null;')
}
$failed=@($checks.GetEnumerator()|Where-Object{-not $_.Value})
foreach($item in $checks.GetEnumerator()){$status=if($item.Value){'PASS'}else{'FAIL'};Write-Host ($status+' - '+$item.Key)}
if($failed.Count -gt 0){throw ('C10.44 static regression failed: '+(($failed|ForEach-Object{$_.Key}) -join ', '))}
Write-Host 'C10.44 static regression PASS.' -ForegroundColor Green
