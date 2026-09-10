param(
  [Parameter(Mandatory=$true)][string]$ModelPath,
  [Parameter(Mandatory=$true)][string]$OutDir
)
$ErrorActionPreference = 'Stop'
$culture = [System.Globalization.CultureInfo]::InvariantCulture
function F([double]$v){ $v.ToString('0.###############',$culture) }
function Add-WrappedIds([System.Collections.Generic.List[string]]$Target, [object[]]$Ids, [int]$Width=16){
  for($i=0; $i -lt $Ids.Count; $i += $Width){
    $last=[Math]::Min($i+$Width-1,$Ids.Count-1)
    $Target.Add((@($Ids[$i..$last]) -join ' '))
  }
}
$model = Get-Content $ModelPath -Raw | ConvertFrom-Json
if($model.schema -ne 'astermax-model-contract/v0'){ throw "Unsupported schema: $($model.schema)" }
if($model.unit_system -ne 'MM_N_S_MPA'){ throw "Production adapter requires MM_N_S_MPA; got $($model.unit_system)" }
if($model.analysis.type -ne 'static_structural'){ throw "Only static_structural is supported in adapter v1" }
if($model.mesh.element_type -ne 'HEXA8'){ throw "Adapter v1 supports HEXA8 solid models only" }
if($model.materials.Count -ne 1){ throw 'Adapter v1 requires exactly one isotropic material.' }
if($model.supports.Count -ne 1){ throw 'Adapter v1 requires exactly one support.' }
if($model.loads.Count -ne 1){ throw 'Adapter v1 requires exactly one load.' }
New-Item -ItemType Directory -Force $OutDir | Out-Null
$base = [IO.Path]::GetFileNameWithoutExtension([IO.Path]::GetFileNameWithoutExtension($ModelPath))
$mailPath = Join-Path $OutDir "$base.mail"
$commPath = Join-Path $OutDir "$base.comm"

$nodes = @($model.mesh.nodes | Sort-Object id)
$elements = @($model.mesh.elements | Sort-Object id)
$groups = $model.mesh.node_groups
if($nodes.Count -lt 1){ throw 'Mesh has no nodes.' }
if($elements.Count -lt 1){ throw 'Mesh has no elements.' }
$mail = New-Object System.Collections.Generic.List[string]
$mail.Add('TITRE')
$mail.Add("ASTERMAX PRODUCTION EXPORT - $($model.name)")
$mail.Add('FINSF')
$mail.Add('COOR_3D')
foreach($n in $nodes){ $mail.Add("$($n.id)  $(F $n.x)  $(F $n.y)  $(F $n.z)") }
$mail.Add('FINSF')
$mail.Add($model.mesh.element_type)
foreach($e in $elements){ $mail.Add("$($e.id) " + (($e.nodes) -join ' ')) }
$mail.Add('FINSF')
foreach($p in $groups.PSObject.Properties | Sort-Object Name){
  $ids=@($p.Value)
  if($ids.Count -lt 1){ throw "Node group $($p.Name) is empty." }
  $mail.Add('GROUP_NO')
  $mail.Add("NOM = $($p.Name)")
  Add-WrappedIds $mail $ids 16
  $mail.Add('FINSF')
}
$mail.Add('FIN')
[IO.File]::WriteAllLines($mailPath,$mail,[Text.UTF8Encoding]::new($false))

$mat = $model.materials[0]
$sup = $model.supports[0]
$load = $model.loads[0]
$loadProp=$groups.PSObject.Properties[$load.group]
$supProp=$groups.PSObject.Properties[$sup.group]
if($null -eq $loadProp){ throw "Load group $($load.group) is missing." }
if($null -eq $supProp){ throw "Support group $($sup.group) is missing." }
$loadNodes = @($loadProp.Value)
if($loadNodes.Count -lt 1){ throw "Load group $($load.group) is empty." }
$fx = [double]$load.fx_total_n / $loadNodes.Count
$fy = [double]$load.fy_total_n / $loadNodes.Count
$fz = [double]$load.fz_total_n / $loadNodes.Count
$checkFx=$fx*$loadNodes.Count; $checkFy=$fy*$loadNodes.Count; $checkFz=$fz*$loadNodes.Count
$tol=1e-10
if([Math]::Abs($checkFx-[double]$load.fx_total_n) -gt $tol -or [Math]::Abs($checkFy-[double]$load.fy_total_n) -gt $tol -or [Math]::Abs($checkFz-[double]$load.fz_total_n) -gt $tol){ throw 'Load conservation check failed before export.' }
$comm = @"
DEBUT()

mesh = LIRE_MAILLAGE(FORMAT='ASTER', UNITE=20)

model = AFFE_MODELE(
    MAILLAGE=mesh,
    AFFE=_F(TOUT='OUI', PHENOMENE='MECANIQUE', MODELISATION='3D'),
)

steel = DEFI_MATERIAU(
    ELAS=_F(E=$(F $mat.young_modulus_mpa), NU=$(F $mat.poisson)),
)

matfield = AFFE_MATERIAU(
    MAILLAGE=mesh,
    AFFE=_F(TOUT='OUI', MATER=steel),
)

fixed = AFFE_CHAR_MECA(
    MODELE=model,
    DDL_IMPO=_F(GROUP_NO='$($sup.group)', DX=$(F $sup.dx), DY=$(F $sup.dy), DZ=$(F $sup.dz)),
)

load = AFFE_CHAR_MECA(
    MODELE=model,
    FORCE_NODALE=_F(GROUP_NO='$($load.group)', FX=$(F $fx), FY=$(F $fy), FZ=$(F $fz)),
)

result = MECA_STATIQUE(
    MODELE=model,
    CHAM_MATER=matfield,
    EXCIT=(
        _F(CHARGE=fixed),
        _F(CHARGE=load),
    ),
)

result = CALC_CHAMP(
    reuse=result,
    RESULTAT=result,
    CONTRAINTE=('SIGM_ELNO',),
    CRITERES=('SIEQ_ELNO',),
)

probe = POST_RELEVE_T(
    ACTION=_F(
        OPERATION='EXTRACTION',
        INTITULE='LOAD_FACE_DISPLACEMENT',
        RESULTAT=result,
        NOM_CHAM='DEPL',
        GROUP_NO='$($model.postprocess.displacement_probe_group)',
        NOM_CMP=('DX','DY','DZ'),
        TOUT_ORDRE='OUI',
    ),
)

IMPR_TABLE(TABLE=probe, UNITE=80)
IMPR_RESU(FORMAT='MED', UNITE=81, RESU=_F(RESULTAT=result))

FIN()
"@
[IO.File]::WriteAllText($commPath,$comm.TrimStart(),[Text.UTF8Encoding]::new($false))
$mailHash=(Get-FileHash $mailPath -Algorithm SHA256).Hash.ToLowerInvariant()
$commHash=(Get-FileHash $commPath -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest = [ordered]@{
  adapter='AsterMax-CodeAster-v1-production'
  source_model=(Resolve-Path $ModelPath).Path
  unit_system=$model.unit_system
  nodes=$nodes.Count
  elements=$elements.Count
  element_type=$model.mesh.element_type
  material=[ordered]@{young_modulus_mpa=[double]$mat.young_modulus_mpa; poisson=[double]$mat.poisson}
  support=[ordered]@{group=$sup.group; dx=[double]$sup.dx; dy=[double]$sup.dy; dz=[double]$sup.dz}
  load=[ordered]@{group=$load.group; fx_total_n=[double]$load.fx_total_n; fy_total_n=[double]$load.fy_total_n; fz_total_n=[double]$load.fz_total_n; fx_per_node_n=$fx; fy_per_node_n=$fy; fz_per_node_n=$fz}
  total_load_n=[math]::Sqrt([math]::Pow([double]$load.fx_total_n,2)+[math]::Pow([double]$load.fy_total_n,2)+[math]::Pow([double]$load.fz_total_n,2))
  load_nodes=$loadNodes.Count
  generated_mail=[IO.Path]::GetFileName($mailPath)
  generated_comm=[IO.Path]::GetFileName($commPath)
  mail_sha256=$mailHash
  comm_sha256=$commHash
  solver_execution='NOT_RUN'
  result_claim='NONE'
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $OutDir "$base.adapter.json") -Encoding UTF8
Write-Host "Generated $mailPath"
Write-Host "Generated $commPath"
Write-Host "Load conservation verified: [$checkFx, $checkFy, $checkFz] N"
Write-Host "SHA256 mail=$mailHash comm=$commHash"
