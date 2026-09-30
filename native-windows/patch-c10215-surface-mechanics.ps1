param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New,[string]$Label) {
    if(-not $Text.Contains($Old)){ throw "C10.24 anchor missing: $Label" }
    return $Text.Replace($Old,$New)
}

$src=Join-Path $PSScriptRoot 'c1024'

# CaeModel frictionless BC
$bc=Join-Path $Root 'CaeModel/Steps/BoundaryConditions/AsterMaxFrictionlessBC.cs'
Copy-Item (Join-Path $src 'AsterMaxFrictionlessBC.cs') $bc -Force
$caeProj=Join-Path $Root 'CaeModel/CaeModel.csproj'
$p=Get-Content $caeProj -Raw
if(-not $p.Contains('Steps\BoundaryConditions\AsterMaxFrictionlessBC.cs')) {
    $anchor='<Compile Include="Steps\BoundaryConditions\FixedBC.cs" />'
    $p=Replace-Required $p $anchor ($anchor+[Environment]::NewLine+'    <Compile Include="Steps\BoundaryConditions\AsterMaxFrictionlessBC.cs" />') 'CaeModel project'
    Set-Content $caeProj $p -Encoding UTF8
}

# StaticStep supports the native AsterMax frictionless BC.
$static=Join-Path $Root 'CaeModel/Steps/StaticStep.cs'
$s=Get-Content $static -Raw
if(-not $s.Contains('boundaryCondition is AsterMaxFrictionlessBC')) {
    $old='                boundaryCondition is SubmodelBC)'
    $new='                boundaryCondition is SubmodelBC ||'+[Environment]::NewLine+'                boundaryCondition is AsterMaxFrictionlessBC)'
    $s=Replace-Required $s $old $new 'StaticStep support'
    Set-Content $static $s -Encoding UTF8
}

# FeModel region validity for a named frictionless surface.
$model=Join-Path $Root 'CaeModel/FeModel.cs'
$m=Get-Content $model -Raw
if(-not $m.Contains('bc is AsterMaxFrictionlessBC')) {
    $anchor='            else if (bc is SubmodelBC sm)'
    $insert=@'
            else if (bc is AsterMaxFrictionlessBC fr)
            {
                valid = fr.RegionType == RegionTypeEnum.SurfaceName && _mesh.Surfaces.ContainsValidKey(fr.RegionName);
            }
            else if (bc is SubmodelBC sm)
'@
    $m=Replace-Required $m $anchor $insert.TrimEnd() 'FeModel frictionless region'
    Set-Content $model $m -Encoding UTF8
}

# Controller draws the frictionless surface instead of throwing for an unknown BC.
$controller=Join-Path $Root 'PrePoMax/Controller.cs'
$c=Get-Content $controller -Raw
if(-not $c.Contains('boundaryCondition is AsterMaxFrictionlessBC')) {
    $anchor='                else if (boundaryCondition is SubmodelBC submodel)'
    $insert=@'
                else if (boundaryCondition is AsterMaxFrictionlessBC frictionless)
                {
                    if (frictionless.RegionType != RegionTypeEnum.SurfaceName) throw new NotSupportedException();
                    if (!_model.Mesh.Surfaces.ContainsKey(frictionless.RegionName)) return;
                    FeSurface surface = _model.Mesh.Surfaces[frictionless.RegionName];
                    count += DrawSurface(prefixName, surface.Name, color, layer, true, false, onlyVisible);
                    if (layer == vtkRendererLayer.Selection)
                        DrawSurfaceEdge(prefixName, surface.Name, color, layer, true, false, onlyVisible);
                }
                else if (boundaryCondition is SubmodelBC submodel)
'@
    $c=Replace-Required $c $anchor $insert.TrimEnd() 'Controller frictionless draw'
    Set-Content $controller $c -Encoding UTF8
}

# Surface mechanics contract and UI.
Copy-Item (Join-Path $src 'AsterMaxSurfaceMechanicsContract.cs') (Join-Path $Root 'PrePoMax/AsterMaxSurfaceMechanicsContract.cs') -Force
Copy-Item (Join-Path $src 'AsterMaxSurfaceMechanicsUi.cs') (Join-Path $Root 'PrePoMax/Forms/AsterMaxSurfaceMechanicsUi.cs') -Force

# Replace the final native exporter implementation with C10.24 surface mechanics.
$exportText=Get-Content (Join-Path $src 'AsterMaxCodeAsterSurfaceExporter.cs') -Raw
$exportText=$exportText.Replace('AsterMaxCodeAsterSurfaceExporter','AsterMaxCodeAsterNativeExporter')
Set-Content (Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs') $exportText -Encoding UTF8

# Compile new PrePoMax sources.
$preProj=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$pp=Get-Content $preProj -Raw
if(-not $pp.Contains('AsterMaxSurfaceMechanicsContract.cs')) {
    $anchor='<Compile Include="Forms\AsterMaxMechanicalQualification.cs" />'
    $insert=$anchor+[Environment]::NewLine+'    <Compile Include="AsterMaxSurfaceMechanicsContract.cs" />'+[Environment]::NewLine+'    <Compile Include="Forms\AsterMaxSurfaceMechanicsUi.cs" />'
    $pp=Replace-Required $pp $anchor $insert 'PrePoMax project'
    Set-Content $preProj $pp -Encoding UTF8
}

# Expose Pressure and Frictionless as first-class Environment commands.
$ui=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $ui -Raw
if(-not $u.Contains('CreateAsterMaxFrictionlessSupport')) {
    $anchor='                CommandTile("Loads", "MODEL", () => AsterMaxC1004MaterialAction(() => tsmiCreateLoad_Click(null, EventArgs.Empty))),'
    $insert=$anchor+[Environment]::NewLine+'                CommandTile("Pressure", "LOAD", () => CreateAsterMaxPressure()),'+[Environment]::NewLine+'                CommandTile("Frictionless", "SUPPORT", () => CreateAsterMaxFrictionlessSupport()),'
    $u=Replace-Required $u $anchor $insert 'native UI commands'
    Set-Content $ui $u -Encoding UTF8
}

Write-Host 'C10.24 Pressure=PRES_REP + Frictionless=FACE_IMPO/DNOR + displacement/multi-load surface backend applied.' -ForegroundColor Green
