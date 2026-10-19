param([string]$Root)
$ErrorActionPreference='Stop'
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $controllerPath)){throw "C10.84 missing: $controllerPath"}
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")

# C10.44 already replaces the serial GeometryDeflection expression with
# asterMaxVisualDeflectionText and formats it with InvariantCulture. Keep this
# candidate idempotent so it can also protect older serial-only pipelines.
$old='                                  _settings.Graphics.GeometryDeflection.ToString();'
$new='                                  _settings.Graphics.GeometryDeflection.ToString(System.Globalization.CultureInfo.InvariantCulture);'
$adaptiveDecl='string asterMaxVisualDeflectionText = asterMaxVisualDeflection.ToString(System.Globalization.CultureInfo.InvariantCulture);'
$adaptiveUse='                                  asterMaxVisualDeflectionText;'

if($c.Contains($old)){
    $c=$c.Replace($old,$new)
    Write-Host 'C10.84: serial NetGen BREP_VISUALIZATION deflection forced to InvariantCulture.' -ForegroundColor Green
}
elseif($c.Contains($new)){
    Write-Host 'C10.84: serial invariant formatting already present.' -ForegroundColor Green
}
elseif($c.Contains($adaptiveDecl) -and $c.Contains($adaptiveUse)){
    Write-Host 'C10.84: C10.44 adaptive preview already provides invariant NetGen numeric formatting; no duplicate rewrite required.' -ForegroundColor Green
}
else {
    throw 'C10.84 invariant NetGen deflection formatting contract missing.'
}

Set-Content $controllerPath $c -Encoding UTF8
