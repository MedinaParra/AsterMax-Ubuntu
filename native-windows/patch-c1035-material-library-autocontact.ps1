param([string]$Root)
$ErrorActionPreference='Stop'

$controllerPath = Join-Path $Root 'PrePoMax/Controller.cs'
$globalsPath = Join-Path $Root 'PrePoMax/Globals.cs'
$assemblyPath = Join-Path $Root 'PrePoMax/Properties/AssemblyInfo.cs'
foreach($p in @($controllerPath,$globalsPath,$assemblyPath)){ if(!(Test-Path $p)){ throw "C10.35 missing: $p" } }

# Canonical default material: use the same name and elastic reference as materials.lib.
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")
$old='public const string AsterMaxDefaultMaterialName = "Acero estructural - AsterMax";'
$new='public const string AsterMaxDefaultMaterialName = "Acero_Estructural";'
if($c.Contains($old)){ $c=$c.Replace($old,$new) }
elseif(-not $c.Contains($new)){ throw 'C10.35 default material anchor missing.' }

$oldDesc='material.Description = "Material predeterminado AsterMax. Revise propiedades antes del cálculo final.";'
$newDesc='material.Description = "Material predeterminado AsterMax, equivalente a la entrada canónica Acero_Estructural de materials.lib (etiqueta humana: Acero estructural). E=210 GPa, nu=0.30, rho=7850 kg/m^3. Revise grado, certificado y condición real antes del cálculo final.";'
if($c.Contains($oldDesc)){ $c=$c.Replace($oldDesc,$newDesc) }
elseif(-not $c.Contains('equivalente a la entrada canónica Acero_Estructural de materials.lib')){ throw 'C10.35 material description anchor missing.' }

# Keep automatic contact generation as a mandatory model-ready behavior.
if(-not $c.Contains('AsterMaxEnsureDefaultMaterialAndSections()')){ throw 'C10.35 default material routine missing after patch chain.' }
$c=$c.Replace('GetNextNumberedKey("AsterMax Auto Section")','GetNextNumberedKey("AsterMax_Auto_Section")')
Set-Content $controllerPath $c -Encoding UTF8

$g=[regex]::Replace((Get-Content $globalsPath -Raw),"\r\n?","`n")
if($g.Contains('AsterMax Mechanical C10.34')){ $g=$g.Replace('AsterMax Mechanical C10.34','AsterMax Mechanical C10.35') }
elseif(-not $g.Contains('AsterMax Mechanical C10.35')){ throw 'C10.35 Globals version anchor missing.' }
Set-Content $globalsPath $g -Encoding UTF8

$a=[regex]::Replace((Get-Content $assemblyPath -Raw),"\r\n?","`n")
$a=$a.Replace('10.34.0.0','10.35.0.0').Replace('C10.34','C10.35')
Set-Content $assemblyPath $a -Encoding UTF8

# Static contract checks: these are build-time guards, not substitutes for runtime tests.
$mainPath = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$m=Get-Content $mainPath -Raw
$u=Get-Content $uiPath -Raw
if(-not $m.Contains('BeginInvoke(new Action(AsterMaxAutoGenerateContacts))')){ throw 'C10.35 automatic contact post-mesh hook missing.' }
if(-not $m.Contains('_controller.AsterMaxEnsureDefaultMaterialAndSections();')){ throw 'C10.35 automatic material assignment hook missing.' }
if(-not $u.Contains('private void AsterMaxAutoGenerateContacts()')){ throw 'C10.35 automatic contact generator missing.' }


# Make auto-contact independent of whether the user meshes all bodies in one batch.
# Once the FE model contains 2+ mesh parts and the current meshing operation succeeded,
# generate contacts when none exist.
$mainPath = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$fm=[regex]::Replace((Get-Content $mainPath -Raw),"\r\n?","`n")
$oldHook='if(errors.Count==0 && partNames.Length>1 && _controller.GetContactPairNames().Length==0)'
$newHook='if(errors.Count==0 && _controller.Model != null && _controller.Model.Mesh != null && _controller.Model.Mesh.Parts.Count>1 && _controller.GetContactPairNames().Length==0)'
if($fm.Contains($oldHook)){ $fm=$fm.Replace($oldHook,$newHook) }
elseif(-not $fm.Contains($newHook)){ throw 'C10.35 post-mesh automatic contact condition anchor missing.' }
Set-Content $mainPath $fm -Encoding UTF8

# Engineering-integrity guard: the current native Code_Aster exporter does not yet
# translate AsterMax ContactPair objects. Never silently solve a detected-contact
# assembly as a no-contact linear static model.
$bridgePath = Join-Path $Root 'PrePoMax/AsterMaxModelContractBridge.cs'
if(!(Test-Path $bridgePath)){ throw 'C10.35 native model contract bridge missing.' }
$b=[regex]::Replace((Get-Content $bridgePath -Raw),"\r\n?","`n")
$guardAnchor='            if (model.Mesh.Elements == null || model.Mesh.Elements.Count == 0) throw new InvalidOperationException("Model mesh contains no elements.");'
$guardNew=$guardAnchor+"`n"+'            if (model.ContactPairs != null && model.ContactPairs.Count > 0) throw new NotSupportedException("C10.35: contact pairs are present, but native Code_Aster contact translation is not yet certified. Solve is blocked to prevent a false no-contact result.");'
if(-not $b.Contains('native Code_Aster contact translation is not yet certified')){
    if(-not $b.Contains($guardAnchor)){ throw 'C10.35 contact fail-closed bridge anchor missing.' }
    $b=$b.Replace($guardAnchor,$guardNew)
}
Set-Content $bridgePath $b -Encoding UTF8
# Runtime audit integration: copy the C10.35 audit partial class, compile it, and
# arm it only when ASTERMAX_C1035_AUDIT_DIR is present.
$auditSource = Join-Path $PSScriptRoot 'AsterMaxC1035Audit.cs'
$auditTarget = Join-Path $Root 'PrePoMax/Forms/AsterMaxC1035Audit.cs'
if(!(Test-Path $auditSource)){ throw 'C10.35 audit source is missing.' }
Copy-Item $auditSource $auditTarget -Force

$projectPath = Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$p=[regex]::Replace((Get-Content $projectPath -Raw),"\r\n?","`n")
$compileAnchor='<Compile Include="Forms\AsterMaxC1034Audit.cs" />'
$compileNew=$compileAnchor+"`n    "+'<Compile Include="Forms\AsterMaxC1035Audit.cs" />'
if(-not $p.Contains('Forms\AsterMaxC1035Audit.cs')){
    if(-not $p.Contains($compileAnchor)){ throw 'C10.35 project audit include anchor missing.' }
    $p=$p.Replace($compileAnchor,$compileNew)
}
Set-Content $projectPath $p -Encoding UTF8

$nativeUiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$n=[regex]::Replace((Get-Content $nativeUiPath -Raw),"\r\n?","`n")
$hookAnchor='                StartAsterMaxC1034OutlineAudit();'
$hookNew=$hookAnchor+"`n"+'                StartAsterMaxC1035DefaultsAudit();'
if(-not $n.Contains('StartAsterMaxC1035DefaultsAudit();')){
    if(-not $n.Contains($hookAnchor)){ throw 'C10.35 audit startup hook anchor missing.' }
    $n=$n.Replace($hookAnchor,$hookNew)
}
Set-Content $nativeUiPath $n -Encoding UTF8

Write-Host 'C10.35: canonical structural steel + automatic contacts/material contract verified.' -ForegroundColor Green
