param([string]$Root)
$ErrorActionPreference='Stop'

$source = Join-Path $PSScriptRoot 'AsterMaxSpanishChile.cs'
if(-not (Test-Path $source)){ throw 'C10.21 es-CL localization source missing.' }

$target = Join-Path $Root 'PrePoMax/Forms/AsterMaxSpanishChile.cs'
Copy-Item $source $target -Force

$proj = Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$p = Get-Content $proj -Raw
$anchor = '<Compile Include="Forms\AsterMaxNativeUi.cs" />'
if(-not $p.Contains($anchor)){ throw 'C10.21 AsterMaxNativeUi project anchor missing.' }
if(-not $p.Contains('Forms\AsterMaxSpanishChile.cs')){
    $p = $p.Replace($anchor, $anchor + [Environment]::NewLine + '    <Compile Include="Forms\AsterMaxSpanishChile.cs" />')
    Set-Content $proj $p -Encoding UTF8
}

$ui = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u = [regex]::Replace((Get-Content $ui -Raw), "\r\n?", "`n")
$hook = '                ThemeRecursive(this);'
if(-not $u.Contains('AsterMaxSpanishChile.Start(this);')){
    if(-not $u.Contains($hook)){ throw 'C10.21 localization hook anchor missing.' }
    $u = $u.Replace($hook, $hook + "`n                AsterMaxSpanishChile.Start(this);")
}
Set-Content $ui $u -Encoding UTF8

# Product-facing identity and initial chrome are Spanish before the runtime translator starts.
$u = [regex]::Replace((Get-Content $ui -Raw), "\r\n?", "`n")
$replacements = [ordered]@{
    'Text = "Mechanical Analysis"' = 'Text = "Análisis mecánico"'
    'Text = "Code_Aster ready path"' = 'Text = "Code_Aster listo"'
    'BuildRibbonPage("Home"' = 'BuildRibbonPage("Inicio"'
    'BuildRibbonPage("Geometry"' = 'BuildRibbonPage("Geometría"'
    'BuildRibbonPage("Model"' = 'BuildRibbonPage("Modelo"'
    'BuildRibbonPage("Connections"' = 'BuildRibbonPage("Conexiones"'
    'BuildRibbonPage("Mesh"' = 'BuildRibbonPage("Malla"'
    'BuildRibbonPage("Environment"' = 'BuildRibbonPage("Entorno"'
    'BuildRibbonPage("Solution"' = 'BuildRibbonPage("Solución"'
    'BuildRibbonPage("Results"' = 'BuildRibbonPage("Resultados"'
    'BuildRibbonPage("View"' = 'BuildRibbonPage("Vista"'
    'Text = "Outline"' = 'Text = "Árbol del modelo"'
    'Text = "Graphics"' = 'Text = "Gráficos"'
}
foreach($kv in $replacements.GetEnumerator()) { $u = $u.Replace($kv.Key,$kv.Value) }
Set-Content $ui $u -Encoding UTF8

# Translate the native model-tree section names without changing internal identifiers.
$modelTree = Join-Path $Root 'UserControls/ModelTree.cs'
$m = Get-Content $modelTree -Raw
$m = $m.Replace('private string _geomPartsName = "Geometry";','private string _geomPartsName = "Geometría";')
$m = $m.Replace('private string _meshingParametersName = "Mesh Controls";','private string _meshingParametersName = "Controles de malla";')
$m = $m.Replace('private string _meshRefinementsName = "Local Mesh Controls";','private string _meshRefinementsName = "Controles locales de malla";')
$m = $m.Replace('private string _boundaryConditionsName = "Supports / BCs";','private string _boundaryConditionsName = "Apoyos / CC";')
$m = $m.Replace('private string _loadsName = "Loads";','private string _loadsName = "Cargas";')
$m = $m.Replace('private string _analysesName = "Solution";','private string _analysesName = "Solución";')
Set-Content $modelTree $m -Encoding UTF8

# AsterMax messages introduced by our patch chain: user-visible text only.
Get-ChildItem (Join-Path $Root 'PrePoMax') -Recurse -Filter '*.cs' | ForEach-Object {
    $path = $_.FullName
    $t = Get-Content $path -Raw
    $before = $t
    $t = $t.Replace('Errors occurred during meshing. Please check the output window.','Ocurrieron errores durante el mallado. Revisa la ventana de salida.')
    $t = $t.Replace('Material assignment incomplete: ','Asignación de material incompleta: ')
    $t = $t.Replace('Inactive or invalid support: ','Apoyo inactivo o inválido: ')
    $t = $t.Replace('Inactive or invalid load: ','Carga inactiva o inválida: ')
    $t = $t.Replace('Node group is empty or contains missing mesh nodes: ','El grupo de nodos está vacío o contiene nodos inexistentes: ')
    if($t -ne $before){ Set-Content $path $t -Encoding UTF8 }
}

Write-Host 'C10.21: interfaz Windows localizada a español de Chile (es-CL).' -ForegroundColor Green
