param([string]$Root)
$ErrorActionPreference='Stop'
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $controllerPath)){throw "C10.84 missing: $controllerPath"}
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")
$old='                                  _settings.Graphics.GeometryDeflection.ToString();'
$new='                                  _settings.Graphics.GeometryDeflection.ToString(System.Globalization.CultureInfo.InvariantCulture);'
if($c.Contains($old)){
    $c=$c.Replace($old,$new)
}
elseif(-not $c.Contains($new)){
    throw 'C10.84 serial NetGen deflection formatting anchor missing.'
}
Set-Content $controllerPath $c -Encoding UTF8
Write-Host 'C10.84: serial NetGen BREP_VISUALIZATION deflection now uses InvariantCulture.' -ForegroundColor Green
